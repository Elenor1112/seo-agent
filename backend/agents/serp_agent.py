"""
SERP Analysis Agent
===================
Fetches SERP results for a list of keywords, extracts competitive signals
from top-ranking pages, and stores snapshots used by the Optimizer agent.

Inputs:  project_id, keyword_ids (list), country_code
Outputs: SerpSnapshot records in PostgreSQL
Queue:   serp
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

from core.config import settings
from core.logging import get_logger
from db.models import Keyword, SerpSnapshot
from db.worker_session import create_worker_session_factory
from integrations.serp.dataforseo_client import DataForSEOClient

logger = get_logger("serp_agent")


class SerpAgent:
    """
    Retrieves SERP data for keyword opportunities and enriches each
    result with content signals extracted from the live pages.
    """

    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.serp_client = DataForSEOClient()

    # ── Main entry point ───────────────────────────────────────────────────

    async def run(
        self,
        keyword_ids: list[str],
        country_code: str = "en",
        top_n: int = 10,
    ) -> dict:
        logger.info("serp_agent.start", keywords=len(keyword_ids))

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            result = await session.execute(
                select(Keyword).where(Keyword.id.in_(keyword_ids))
            )
            keywords = result.scalars().all()

        snapshots_saved = 0
        # Process in batches of 10 to stay within rate limits
        batch_size = 10
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i:i + batch_size]
            tasks = [self._process_keyword(kw, country_code, top_n) for kw in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, int):
                    snapshots_saved += r
            await asyncio.sleep(1)  # respect rate limit

        logger.info("serp_agent.complete", snapshots=snapshots_saved)
        return {"snapshots_saved": snapshots_saved, "keywords_processed": len(keywords)}

    # ── Per-keyword processing ─────────────────────────────────────────────

    async def _process_keyword(
        self,
        keyword: Keyword,
        country_code: str,
        top_n: int,
    ) -> int:
        try:
            serp_results = await self.serp_client.organic_search(
                query=keyword.query,
                location_code=2840,  # USA default
                language_code=country_code,
                depth=top_n,
            )
        except Exception as exc:
            logger.warning("serp_agent.fetch_error", keyword=keyword.query, error=str(exc))
            return 0

        saved = 0
        paa_questions = self._extract_paa(serp_results)

        for item in serp_results.get("organic_results", [])[:top_n]:
            try:
                snapshot = await self._build_snapshot(keyword, item, paa_questions)
                await self._save_snapshot(snapshot)
                saved += 1
            except Exception as exc:
                logger.warning("serp_agent.snapshot_error", url=item.get("url"), error=str(exc))

        return saved

    async def _build_snapshot(
        self,
        keyword: Keyword,
        item: dict,
        paa_questions: list[str],
    ) -> dict:
        url = item.get("url", "")
        # Optionally fetch the live page to extract deeper signals
        content_signals = await self._fetch_page_signals(url)

        return {
            "keyword_id": str(keyword.id),
            "position": item.get("rank_absolute", 99),
            "url": url,
            "title": item.get("title", "")[:512],
            "meta_description": item.get("description", ""),
            "domain": item.get("domain", ""),
            "word_count": content_signals.get("word_count"),
            "schema_types": content_signals.get("schema_types", []),
            "has_featured_snippet": item.get("featured_snippet", False),
            "has_faq_schema": "FAQPage" in content_signals.get("schema_types", []),
            "paa_questions": paa_questions,
            "entities": content_signals.get("entities", []),
            "h2_headings": content_signals.get("h2_headings", []),
        }

    async def _fetch_page_signals(self, url: str) -> dict:
        """Fetch a SERP result page and extract content signals."""
        if not url or not url.startswith("http"):
            return {}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; SEOAgent/1.0)"}
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    return {}
                return self._parse_page_signals(resp.text, url)
        except Exception:
            return {}

    def _parse_page_signals(self, html: str, base_url: str) -> dict:
        soup = BeautifulSoup(html, "lxml")

        # Remove nav/footer/ads for accurate word count
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        body_text = soup.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())

        h2s = [h.get_text(strip=True) for h in soup.find_all("h2")][:20]

        # Schema types from JSON-LD
        import json, re
        schema_types: list[str] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict) and data.get("@type"):
                    schema_types.append(data["@type"])
                elif isinstance(data, list):
                    schema_types.extend(item.get("@type", "") for item in data if item.get("@type"))
            except Exception:
                pass

        # Simple entity extraction: proper nouns (NNP) from text
        # In V2, replace with spaCy NER
        entities = list(set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', body_text)))[:30]

        return {
            "word_count": word_count,
            "h2_headings": h2s,
            "schema_types": list(set(schema_types)),
            "entities": entities,
        }

    def _extract_paa(self, serp_results: dict) -> list[str]:
        """Extract People Also Ask questions from SERP response."""
        questions = []
        for item in serp_results.get("related_questions", []):
            if q := item.get("question"):
                questions.append(q)
        return questions[:10]

    async def _save_snapshot(self, snapshot: dict) -> None:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            stmt = pg_insert(SerpSnapshot).values(
                keyword_id=snapshot["keyword_id"],
                position=snapshot["position"],
                url=snapshot["url"],
                title=snapshot["title"],
                meta_description=snapshot.get("meta_description", ""),
                domain=snapshot.get("domain", ""),
                word_count=snapshot.get("word_count"),
                schema_types=snapshot.get("schema_types", []),
                has_featured_snippet=snapshot.get("has_featured_snippet", False),
                has_faq_schema=snapshot.get("has_faq_schema", False),
                paa_questions=snapshot.get("paa_questions", []),
                entities=snapshot.get("entities", []),
                h2_headings=snapshot.get("h2_headings", []),
                scraped_at=datetime.now(timezone.utc),
            )
            await session.execute(stmt)
            await session.commit()

"""
Keyword Agent
=============
Pulls query data from Google Search Console, clusters keywords by semantic
intent, scores opportunities, and persists ranked keyword records.

If GSC is not connected (no property URL or no rows returned), falls back to
extracting candidate keywords from crawled Page records for the project.
Optionally accepts seed_keywords passed at run time to supplement either source.

Inputs:  project_id, date_range_days (default 480 = ~16 months)
         seed_keywords (optional list[str])
Outputs: Keyword records in PostgreSQL with opportunity scores
Queue:   keywords
"""
from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from core.config import settings
from core.logging import get_logger
from db.models import Keyword, Page, Project, SearchIntent
from db.worker_session import create_worker_session_factory
from integrations.gsc.client import GSCClient
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = get_logger("keyword_agent")


class KeywordAgent:
    """
    Fetches GSC data, clusters keywords by embedding similarity,
    classifies search intent, and computes opportunity scores.

    Falls back to crawl-derived keywords when GSC is unavailable.
    """

    # Position ranges for opportunity classification (GSC source)
    GAP_MIN_POSITION = 8
    GAP_MAX_POSITION = 30
    GAP_MIN_IMPRESSIONS = 100

    # Crawl fallback: minimum word length to keep as a keyword candidate
    MIN_KEYWORD_WORD_LENGTH = 2
    MAX_CRAWL_KEYWORDS = 500

    def __init__(self, project: Project) -> None:
        self.project = project

    # ── Main entry point ───────────────────────────────────────────────────

    async def run(
        self,
        date_range_days: int = 480,
        seed_keywords: list[str] | None = None,
    ) -> dict:
        logger.info("keyword_agent.start", project=str(self.project.id))

        rows: list[dict] = []
        source = "gsc"

        # 1. Try GSC first
        if self.project.gsc_property_url:
            gsc = GSCClient(self.project)
            end_date = datetime.now(timezone.utc).date()
            start_date = end_date - timedelta(days=date_range_days)

            rows = await gsc.fetch_queries(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                row_limit=25000,
            )
            logger.info("keyword_agent.gsc_rows", count=len(rows))
        else:
            logger.warning("gsc.no_property_url", project=str(self.project.id))

        # 2. Crawl fallback — extract keywords from pages if GSC gave nothing
        if not rows:
            logger.info("keyword_agent.crawl_fallback", project=str(self.project.id))
            rows = await self._extract_keywords_from_pages()
            source = "crawl"
            logger.info("keyword_agent.crawl_rows", count=len(rows))

        # 3. Merge in seed keywords (deduplicated)
        if seed_keywords:
            existing_queries = {r["query"].lower() for r in rows}
            for kw in seed_keywords:
                kw = kw.strip()
                if kw and kw.lower() not in existing_queries:
                    rows.append(self._seed_row(kw))
                    existing_queries.add(kw.lower())
            logger.info("keyword_agent.seed_merged", total=len(rows))

        if not rows:
            logger.warning("keyword_agent.no_rows", project=str(self.project.id))
            return {"keywords_processed": 0, "gaps_found": 0, "source": source}

        # 4. Enrich (opportunity score, intent, gap flag)
        enriched = [self._enrich_row(row) for row in rows]

        # 5. Embed and cluster
        queries = [r["query"] for r in enriched]
        embeddings = await self._embed_queries(queries)
        n_clusters = max(3, min(len(queries) // 20, 50))
        cluster_labels = self._cluster_keywords(embeddings, n_clusters=n_clusters)

        # 6. Assign cluster IDs and human-readable labels
        cluster_map: dict[int, str] = {}
        cluster_name_map: dict[int, str] = {}
        for label in set(cluster_labels):
            cluster_map[label] = str(uuid.uuid4())
            members = [enriched[i] for i, l in enumerate(cluster_labels) if l == label]
            top = max(members, key=lambda r: r["impressions"])
            cluster_name_map[label] = top["query"][:100]

        for i, row in enumerate(enriched):
            lbl = cluster_labels[i]
            row["cluster_id"] = cluster_map[lbl]
            row["cluster_label"] = cluster_name_map[lbl]

        # 7. Persist
        await self._persist_keywords(enriched)

        gaps = sum(1 for r in enriched if r["is_gap"])
        logger.info("keyword_agent.complete", total=len(enriched), gaps=gaps, source=source)
        return {"keywords_processed": len(enriched), "gaps_found": gaps, "source": source}

    # ── Crawl-based keyword extraction ────────────────────────────────────

    async def _extract_keywords_from_pages(self) -> list[dict]:
        """
        Extract keyword candidates from crawled Page records.

        Sources (in priority order):
          - title tag
          - H1
          - H2 headings (from h_tags JSONB)
          - meta description
          - H3 headings

        Each unique n-gram phrase becomes a candidate keyword row with
        zero GSC metrics (impressions/clicks/ctr/position all null/0).
        """
        SessionLocal = create_worker_session_factory()
        pages: list[Page] = []

        async with SessionLocal() as session:
            result = await session.execute(
                select(Page).where(
                    Page.project_id == self.project.id,
                    Page.is_indexable == True,
                    Page.http_status == 200,
                )
            )
            pages = result.scalars().all()

        if not pages:
            logger.warning("keyword_agent.no_pages", project=str(self.project.id))
            return []

        candidates: dict[str, int] = {}  # query -> frequency

        for page in pages:
            phrases = []

            # Title — highest signal
            if page.title:
                phrases += self._split_phrases(page.title, weight=3)

            # H1
            if page.h1:
                phrases += self._split_phrases(page.h1, weight=3)

            # H2s and H3s from h_tags JSONB
            if page.h_tags:
                for h2 in page.h_tags.get("h2", []):
                    phrases += self._split_phrases(h2, weight=2)
                for h3 in page.h_tags.get("h3", []):
                    phrases += self._split_phrases(h3, weight=1)

            # Meta description — lower signal
            if page.meta_description:
                phrases += self._split_phrases(page.meta_description, weight=1)

            for phrase in phrases:
                candidates[phrase] = candidates.get(phrase, 0) + 1

        # Sort by frequency, cap at MAX_CRAWL_KEYWORDS
        sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
        sorted_candidates = sorted_candidates[: self.MAX_CRAWL_KEYWORDS]

        return [
            {
                "query": phrase,
                "impressions": 0,
                "clicks": 0,
                "ctr": 0.0,
                "position": None,  # unknown — no GSC
                "source": "crawl",
            }
            for phrase, _ in sorted_candidates
        ]

    def _split_phrases(self, text: str, weight: int = 1) -> list[str]:
        """
        Extract meaningful phrases from a text string.

        Returns individual words (2+ chars) and bigrams/trigrams,
        lowercased and cleaned. Weight controls how many times each
        phrase is emitted (simulating importance).
        """
        # Strip HTML tags if any leaked through
        text = re.sub(r"<[^>]+>", " ", text)
        # Lowercase, keep only letters, numbers, spaces
        text = re.sub(r"[^\w\s]", " ", text.lower())
        words = [w for w in text.split() if len(w) >= self.MIN_KEYWORD_WORD_LENGTH and not w.isdigit()]

        phrases = []

        # Unigrams
        phrases += words

        # Bigrams
        phrases += [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

        # Trigrams
        phrases += [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words) - 2)]

        return phrases * weight

    def _seed_row(self, keyword: str) -> dict:
        """Build a minimal keyword row from a user-supplied seed."""
        return {
            "query": keyword,
            "impressions": 0,
            "clicks": 0,
            "ctr": 0.0,
            "position": None,
            "source": "seed",
        }

    # ── Enrichment ─────────────────────────────────────────────────────────

    def _enrich_row(self, row: dict) -> dict:
        """Add opportunity score, gap flag, and intent classification."""
        query = row["query"]
        impressions = row.get("impressions", 0)
        clicks = row.get("clicks", 0)
        ctr = row.get("ctr", 0.0)
        position = row.get("position")  # may be None for crawl/seed rows

        # Gap only applies to GSC rows with real position data
        is_gap = (
            position is not None
            and self.GAP_MIN_POSITION <= position <= self.GAP_MAX_POSITION
            and impressions >= self.GAP_MIN_IMPRESSIONS
        )

        # Opportunity score
        if position is not None:
            pos_score = max(0.0, (100 - position) / 100)
        else:
            # No position data — assign a neutral mid-range score
            pos_score = 0.5

        impression_score = min(1.0, math.log1p(impressions) / math.log1p(10000))
        ctr_gap_score = max(0.0, 1.0 - ctr) if is_gap else 0.0
        opportunity_score = round(
            (pos_score * 0.4 + impression_score * 0.4 + ctr_gap_score * 0.2) * 100, 2
        )

        intent = self._classify_intent(query)

        return {
            **row,
            "is_gap": is_gap,
            "opportunity_score": opportunity_score,
            "search_intent": intent,
            "cluster_id": None,
            "cluster_label": None,
        }

    def _classify_intent(self, query: str) -> str:
        """Rule-based intent classification (replace with LLM in V2)."""
        q = query.lower()
        transactional_signals = ["buy", "price", "order", "purchase", "checkout", "deal", "discount", "shop"]
        commercial_signals = ["best", "top", "review", "compare", "vs", "alternative", "comparison"]
        navigational_signals = ["login", "sign in", "account", "download", "install"]

        if any(s in q for s in transactional_signals):
            return SearchIntent.transactional
        if any(s in q for s in commercial_signals):
            return SearchIntent.commercial
        if any(s in q for s in navigational_signals):
            return SearchIntent.navigational
        return SearchIntent.informational

    # ── Embeddings & clustering ────────────────────────────────────────────

    async def _embed_queries(self, queries: list[str]) -> np.ndarray:
        """Generate sentence embeddings using local model."""
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            return model.encode(queries, batch_size=64, show_progress_bar=False)
        except Exception as exc:
            logger.warning("keyword_agent.embedding_fallback", error=str(exc))
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(max_features=500)
            return vec.fit_transform(queries).toarray()

    def _cluster_keywords(self, embeddings: np.ndarray, n_clusters: int) -> list[int]:
        n_clusters = min(n_clusters, len(embeddings))
        clustering = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric="cosine",
            linkage="average",
        )
        return clustering.fit_predict(embeddings).tolist()

    # ── Persistence ────────────────────────────────────────────────────────

    async def _persist_keywords(self, rows: list[dict]) -> None:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            for row in rows:
                stmt = pg_insert(Keyword).values(
                    project_id=self.project.id,
                    query=row["query"],
                    impressions=row.get("impressions", 0),
                    clicks=row.get("clicks", 0),
                    ctr=row.get("ctr", 0.0),
                    avg_position=row.get("position"),
                    opportunity_score=row.get("opportunity_score"),
                    search_intent=row.get("search_intent"),
                    is_gap=row.get("is_gap", False),
                    cluster_id=row.get("cluster_id"),
                    cluster_label=row.get("cluster_label"),
                    last_gsc_sync=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    constraint="uq_keyword_project_query",
                    set_={
                        "impressions": row.get("impressions", 0),
                        "clicks": row.get("clicks", 0),
                        "ctr": row.get("ctr", 0.0),
                        "avg_position": row.get("position"),
                        "opportunity_score": row.get("opportunity_score"),
                        "is_gap": row.get("is_gap", False),
                        "cluster_id": row.get("cluster_id"),
                        "cluster_label": row.get("cluster_label"),
                        "last_gsc_sync": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)
            await session.commit()
        logger.info("keyword_agent.persisted", count=len(rows))
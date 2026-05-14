"""
Crawler Agent
=============
Performs a full technical SEO audit of a project's website.

Inputs:  project_id, start_url, max_depth, max_pages
Outputs: Page records in PostgreSQL, crawl summary in ClickHouse
Queue:   crawl
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import extruct
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page as PlaywrightPage
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import settings
from core.logging import get_logger
from db.models import Page, Project, TaskStatus
from db.worker_session import create_worker_session_factory

logger = get_logger("crawler_agent")


class CrawlerAgent:
    """
    Crawls a website using Playwright, extracts SEO signals from each page,
    and persists structured records to PostgreSQL.
    """

    SKIP_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
        ".pdf", ".zip", ".gz", ".mp4", ".mp3", ".css", ".js",
        ".woff", ".woff2", ".ttf", ".ico",
    }

    def __init__(self, project: Project) -> None:
        self.project = project
        self.base_url = project.base_url.rstrip("/")
        self.domain = urlparse(self.base_url).netloc
        self.visited: set[str] = set()
        self.queue: deque[tuple[str, int]] = deque()  # (url, depth)
        self.results: list[dict] = []

    # ── Public entry point ─────────────────────────────────────────────────

    async def run(
        self,
        max_depth: int = settings.crawler_max_depth,
        max_pages: int = settings.crawler_max_pages,
    ) -> dict:
        logger.info("crawl.start", domain=self.domain, max_depth=max_depth, max_pages=max_pages)
        start = time.time()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            try:
                self.queue.append((self.base_url, 0))
                sem = asyncio.Semaphore(settings.crawler_concurrency)

                while self.queue and len(self.visited) < max_pages:
                    batch = []
                    while self.queue and len(batch) < settings.crawler_concurrency:
                        batch.append(self.queue.popleft())

                    tasks = [
                        self._crawl_page(browser, url, depth, max_depth, sem)
                        for url, depth in batch
                        if url not in self.visited
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                await browser.close()

        await self._persist_results()
        summary = self._build_summary(time.time() - start)
        logger.info("crawl.complete", **summary)
        return summary

    # ── Page crawl ─────────────────────────────────────────────────────────

    async def _crawl_page(
        self,
        browser: Browser,
        url: str,
        depth: int,
        max_depth: int,
        sem: asyncio.Semaphore,
    ) -> None:
        if url in self.visited:
            return
        self.visited.add(url)

        async with sem:
            page = await browser.new_page()
            try:
                page.set_default_timeout(settings.crawler_timeout_ms)
                response = await page.goto(url, wait_until="domcontentloaded")

                if response is None:
                    return

                status = response.status
                final_url = page.url
                html = await page.content()

                page_data = self._extract_seo_data(url, final_url, status, html)

                # Enqueue new internal links if not at max depth
                if depth < max_depth:
                    for link in page_data.get("outgoing_links", []):
                        normalized = self._normalize_url(link)
                        if normalized and normalized not in self.visited:
                            self.queue.append((normalized, depth + 1))

                self.results.append(page_data)
                logger.debug("crawl.page", url=url, status=status, words=page_data.get("word_count"))

            except Exception as exc:
                logger.warning("crawl.page_error", url=url, error=str(exc))
                self.results.append({
                    "url": url,
                    "http_status": 0,
                    "issues": ["crawl_error"],
                    "error": str(exc),
                })
            finally:
                await page.close()

    # ── Extraction ─────────────────────────────────────────────────────────

    def _extract_seo_data(
        self,
        original_url: str,
        final_url: str,
        status: int,
        html: str,
    ) -> dict:
        soup = BeautifulSoup(html, "lxml")
        issues: list[str] = []

        # Redirect detection
        redirect_to = final_url if final_url != original_url else None
        if redirect_to and status in (301, 302, 307, 308):
            issues.append("redirect")

        # Title
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            issues.append("missing_title")
        elif len(title) > 60:
            issues.append("title_too_long")

        # Meta description
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None
        if not meta_description:
            issues.append("missing_meta_description")

        # Canonical
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        canonical_url = canonical_tag.get("href") if canonical_tag else None

        # Robots
        robots_tag = soup.find("meta", attrs={"name": "robots"})
        robots_directives = robots_tag.get("content", "").lower() if robots_tag else None
        is_indexable = True
        if robots_directives and ("noindex" in robots_directives):
            is_indexable = False

        # H-tags
        h_tags: dict[str, list[str]] = {}
        for level in ["h1", "h2", "h3", "h4"]:
            tags = soup.find_all(level)
            h_tags[level] = [t.get_text(strip=True) for t in tags]

        h1_list = h_tags.get("h1", [])
        if not h1_list:
            issues.append("missing_h1")
        elif len(h1_list) > 1:
            issues.append("multiple_h1")

        # Hreflang
        hreflang_tags = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
        hreflang = {tag.get("hreflang"): tag.get("href") for tag in hreflang_tags} or None

        # Structured data (JSON-LD + microdata + RDFa)
        try:
            extracted = extruct.extract(html, base_url=final_url, syntaxes=["json-ld", "microdata"])
            json_ld = extracted.get("json-ld", [])
            schema_types = list({
                item.get("@type", "") for item in json_ld if item.get("@type")
            })
        except Exception:
            json_ld = []
            schema_types = []

        # Word count (visible text)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.get_text(separator=" ", strip=True)
        word_count = len(body_text.split())
        content_hash = hashlib.sha256(body_text.encode()).hexdigest()

        # Internal links
        all_links = soup.find_all("a", href=True)
        internal_links = []
        external_links = []
        for a in all_links:
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                continue
            abs_href = urljoin(final_url, href)
            if urlparse(abs_href).netloc == self.domain:
                internal_links.append(abs_href)
            else:
                external_links.append(abs_href)

        if len(internal_links) == 0 and status == 200:
            issues.append("no_internal_links")

        return {
            "url": original_url,
            "canonical_url": canonical_url,
            "http_status": status,
            "redirect_to": redirect_to,
            "title": title,
            "meta_description": meta_description,
            "h1": h1_list[0] if h1_list else None,
            "h_tags": h_tags,
            "robots_directives": robots_directives,
            "is_indexable": is_indexable,
            "hreflang": hreflang,
            "structured_data": json_ld,
            "schema_types": schema_types,
            "internal_links_out": len(internal_links),
            "word_count": word_count,
            "content_hash": content_hash,
            "issues": issues,
            "outgoing_links": internal_links,  # used for queueing; not persisted directly
        }

    # ── Persistence ────────────────────────────────────────────────────────

    async def _persist_results(self) -> None:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            for data in self.results:
                outgoing = data.pop("outgoing_links", [])
                error = data.pop("error", None)

                stmt = pg_insert(Page).values(
                    project_id=self.project.id,
                    url=data["url"],
                    canonical_url=data.get("canonical_url"),
                    http_status=data.get("http_status"),
                    redirect_to=data.get("redirect_to"),
                    title=data.get("title"),
                    meta_description=data.get("meta_description"),
                    h1=data.get("h1"),
                    h_tags=data.get("h_tags"),
                    robots_directives=data.get("robots_directives"),
                    is_indexable=data.get("is_indexable", True),
                    hreflang=data.get("hreflang"),
                    structured_data=data.get("structured_data"),
                    schema_types=data.get("schema_types"),
                    internal_links_out=data.get("internal_links_out", 0),
                    word_count=data.get("word_count"),
                    content_hash=data.get("content_hash"),
                    issues=data.get("issues", []),
                    crawled_at=datetime.now(timezone.utc),
                ).on_conflict_do_update(
                    constraint="uq_page_project_url",
                    set_={
                        "http_status": data.get("http_status"),
                        "title": data.get("title"),
                        "meta_description": data.get("meta_description"),
                        "h1": data.get("h1"),
                        "h_tags": data.get("h_tags"),
                        "word_count": data.get("word_count"),
                        "content_hash": data.get("content_hash"),
                        "issues": data.get("issues", []),
                        "crawled_at": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)

            # Update internal_links_in counts based on outgoing link graph
            # (simplified: done as a separate aggregation query)
            await session.commit()
        logger.info("crawl.persisted", pages=len(self.results))

    # ── Utilities ──────────────────────────────────────────────────────────

    def _normalize_url(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if parsed.netloc and parsed.netloc != self.domain:
                return None
            ext = "." + parsed.path.rsplit(".", 1)[-1].lower() if "." in parsed.path else ""
            if ext in self.SKIP_EXTENSIONS:
                return None
            # Strip fragments and query strings for dedup
            clean = parsed._replace(fragment="", query="").geturl()
            return clean.rstrip("/")
        except Exception:
            return None

    def _build_summary(self, elapsed: float) -> dict:
        pages = self.results
        issues_flat = [i for p in pages for i in (p.get("issues") or [])]
        return {
            "total_pages": len(pages),
            "indexable_pages": sum(1 for p in pages if p.get("is_indexable", True)),
            "pages_with_issues": sum(1 for p in pages if p.get("issues")),
            "redirect_chains": issues_flat.count("redirect"),
            "missing_meta": issues_flat.count("missing_meta_description"),
            "missing_h1": issues_flat.count("missing_h1"),
            "elapsed_seconds": round(elapsed, 2),
        }

"""
Content Optimizer Agent
=======================
Analyses existing pages against SERP benchmarks and generates targeted
edit-sets (not full rewrites) to close competitive gaps.

Inputs:  project_id, page_id, keyword_id
Outputs: ContentVersion record (type=optimize_diff) with specific edit instructions
Queue:   optimize
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from core.config import settings
from core.logging import get_logger
from db.models import ContentVersion, ContentStatus, Keyword, Page, Project, SerpSnapshot
from db.worker_session import create_worker_session_factory
from integrations.llm.claude_client import ClaudeClient
from services.storage import StorageService

logger = get_logger("optimizer_agent")


SYSTEM_PROMPT = """You are a senior SEO editor. Your job is to improve existing content to
outperform competitors — not by rewriting everything, but by making targeted, high-impact edits.

You analyse gaps between the existing content and the competitive benchmark, then produce
a precise, actionable edit-set with rationale for each change.

Your edit-sets are clear enough for a junior editor to execute without additional context.
You respond in valid JSON only."""


class ContentOptimizerAgent:
    """
    Compares an existing page against SERP competitor benchmarks and
    generates a structured diff/edit-set to close the ranking gaps.
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self.claude = ClaudeClient()
        self.storage = StorageService()

    # ── Main entry point ───────────────────────────────────────────────────

    async def run(self, page_id: str, keyword_id: str) -> dict:
        logger.info("optimizer.start", page_id=page_id, keyword_id=keyword_id)

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            page = await session.get(Page, page_id)
            keyword = await session.get(Keyword, keyword_id)
            if not page or not keyword:
                raise ValueError("Page or keyword not found")

            result = await session.execute(
                select(SerpSnapshot)
                .where(SerpSnapshot.keyword_id == keyword_id)
                .order_by(SerpSnapshot.position)
                .limit(5)
            )
            serp_snapshots = result.scalars().all()

        # Build gap analysis
        gaps = self._analyse_gaps(page, keyword, serp_snapshots)

        if not gaps["has_meaningful_gaps"]:
            logger.info("optimizer.no_gaps", page=page.url)
            return {"status": "no_gaps", "page": page.url}

        # Generate targeted edits
        edit_set = await self._generate_edits(page, keyword, gaps, serp_snapshots)

        # Persist as content version
        version_id = await self._save_edit_set(page, keyword, edit_set, gaps)

        logger.info(
            "optimizer.complete",
            page=page.url,
            edits=len(edit_set.get("edits", [])),
        )
        return {
            "content_version_id": str(version_id),
            "page_url": page.url,
            "gaps_found": gaps["gap_summary"],
            "edits_generated": len(edit_set.get("edits", [])),
        }

    # ── Gap analysis ───────────────────────────────────────────────────────

    def _analyse_gaps(
        self,
        page: Page,
        keyword: Keyword,
        snapshots: list[SerpSnapshot],
    ) -> dict:
        if not snapshots:
            return {"has_meaningful_gaps": False, "gap_summary": {}}

        # Word count gap
        avg_competitor_words = sum(s.word_count or 0 for s in snapshots) // len(snapshots)
        word_count_gap = max(0, avg_competitor_words - (page.word_count or 0))

        # Schema gap
        competitor_schemas = {t for s in snapshots for t in (s.schema_types or [])}
        page_schemas = set(page.schema_types or [])
        missing_schemas = list(competitor_schemas - page_schemas)

        # Heading / topic gap
        competitor_h2s = [h for s in snapshots for h in (s.h2_headings or [])]
        page_h2s = [h for h in (page.h_tags or {}).get("h2", [])]
        page_h2_lower = [h.lower() for h in page_h2s]
        missing_topics: list[str] = []
        for ch2 in competitor_h2s:
            if not any(w in page_h2_lower for w in ch2.lower().split() if len(w) > 4):
                missing_topics.append(ch2)

        # Entity gap
        competitor_entities = {e for s in snapshots for e in (s.entities or [])}
        missing_entities = list(competitor_entities)[:20]

        # PAA gap
        paa_questions = list({q for s in snapshots for q in (s.paa_questions or [])})
        has_faq = "FAQPage" in page_schemas

        has_featured_snippet_opportunity = any(s.has_featured_snippet for s in snapshots)

        has_meaningful_gaps = (
            word_count_gap > 200
            or len(missing_schemas) > 0
            or len(missing_topics) > 2
            or (paa_questions and not has_faq)
        )

        return {
            "has_meaningful_gaps": has_meaningful_gaps,
            "word_count_gap": word_count_gap,
            "avg_competitor_words": avg_competitor_words,
            "page_word_count": page.word_count or 0,
            "missing_schemas": missing_schemas,
            "missing_topics": missing_topics[:10],
            "missing_entities": missing_entities,
            "paa_questions": paa_questions[:8],
            "has_faq_on_page": has_faq,
            "has_featured_snippet_opportunity": has_featured_snippet_opportunity,
            "gap_summary": {
                "word_count_gap": word_count_gap,
                "missing_schemas": len(missing_schemas),
                "missing_topics": len(missing_topics),
                "paa_answered": has_faq,
            },
        }

    # ── Edit generation ────────────────────────────────────────────────────

    async def _generate_edits(
        self,
        page: Page,
        keyword: Keyword,
        gaps: dict,
        snapshots: list[SerpSnapshot],
    ) -> dict:
        prompt = self._build_prompt(page, keyword, gaps)

        response_text = await self.claude.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=4096,
        )

        try:
            edit_set = json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r"```json\s*([\s\S]+?)\s*```", response_text)
            if match:
                edit_set = json.loads(match.group(1))
            else:
                raise ValueError("Claude response was not valid JSON")

        return edit_set

    def _build_prompt(self, page: Page, keyword: Keyword, gaps: dict) -> str:
        return f"""Analyse the following page and generate a targeted edit-set to improve its SEO performance.

PAGE DETAILS:
- URL: {page.url}
- Title: {page.title}
- H1: {page.h1}
- Current H2s: {json.dumps((page.h_tags or {}).get("h2", [])[:10])}
- Word count: {page.word_count or 0}
- Schema types: {json.dumps(page.schema_types or [])}

TARGET KEYWORD: {keyword.query}
CURRENT POSITION: {keyword.avg_position or "unknown"}

COMPETITIVE GAPS IDENTIFIED:
- Word count gap: needs ~{gaps["word_count_gap"]} more words (competitors avg: {gaps["avg_competitor_words"]})
- Missing schema types: {json.dumps(gaps["missing_schemas"])}
- Missing topic areas (from competitor H2s): {json.dumps(gaps["missing_topics"][:8])}
- Missing entities to cover: {json.dumps(gaps["missing_entities"][:10])}
- People Also Ask questions NOT yet answered: {json.dumps(gaps["paa_questions"])}
- Has featured snippet opportunity: {gaps["has_featured_snippet_opportunity"]}

Generate a precise, prioritised edit-set. Each edit must be specific enough to execute without guessing.

Respond with ONLY valid JSON (no markdown):
{{
  "summary": "string (1-2 sentences summarising the main improvements needed)",
  "expected_impact": "string (e.g., '+3 to +7 position improvement based on gap size')",
  "edits": [
    {{
      "edit_type": "string (one of: add_section|expand_section|add_faq|add_schema|rewrite_title|rewrite_meta|add_entity|restructure_heading)",
      "priority": "high|medium|low",
      "target": "string (where to apply: e.g., 'after section about X', 'page title', 'before conclusion')",
      "instruction": "string (precise, actionable instruction for an editor)",
      "content_suggestion": "string (draft content or example to start from)",
      "rationale": "string (why this edit will improve rankings)"
    }}
  ],
  "schema_to_add": [
    {{
      "type": "string (schema.org type)",
      "reason": "string"
    }}
  ]
}}"""

    # ── Persistence ────────────────────────────────────────────────────────

    async def _save_edit_set(
        self,
        page: Page,
        keyword: Keyword,
        edit_set: dict,
        gaps: dict,
    ) -> str:
        # Store full edit-set JSON in S3
        import uuid
        s3_key = f"projects/{self.project.id}/optimizations/{page.id}-{uuid.uuid4().hex[:8]}.json"
        await self.storage.put_json(s3_key, {"gaps": gaps, "edit_set": edit_set})

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            # Get next version number for this page
            result = await session.execute(
                select(ContentVersion.version)
                .where(ContentVersion.page_id == page.id)
                .order_by(ContentVersion.version.desc())
                .limit(1)
            )
            last_version = result.scalar_one_or_none() or 0

            version = ContentVersion(
                project_id=self.project.id,
                page_id=page.id,
                keyword_id=keyword.id,
                version=last_version + 1,
                status=ContentStatus.review,
                content_type="optimize_diff",
                title=edit_set.get("summary", "")[:255],
                target_keyword=keyword.query,
                s3_key=s3_key,
                semantic_score=None,
                generated_by="optimizer_agent",
                prompt_version="v1.0",
                generation_meta={
                    "model": settings.anthropic_model,
                    "gap_summary": gaps.get("gap_summary", {}),
                    "edits_count": len(edit_set.get("edits", [])),
                },
            )
            session.add(version)
            await session.commit()
            await session.refresh(version)
            return str(version.id)

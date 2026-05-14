"""
Content Generation Agent
========================
Generates SEO-optimised content for keyword gap opportunities using
Claude API, guided by SERP competitive data and brand voice settings.

Inputs:  project_id, keyword_id, content_type
Outputs: ContentVersion record in PostgreSQL, HTML/MD blob in S3
Queue:   content
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from core.config import settings
from core.logging import get_logger
from db.models import ContentVersion, ContentStatus, Keyword, Project, SerpSnapshot
from db.worker_session import create_worker_session_factory
from integrations.llm.claude_client import ClaudeClient
from services.storage import StorageService

logger = get_logger("content_gen_agent")


SYSTEM_PROMPT = """You are an expert SEO content strategist and writer. You create high-quality,
comprehensive content that ranks well in search engines while genuinely serving the reader.

Your content always:
- Addresses the search intent directly and completely
- Covers topics competitors miss (entity and subtopic gaps)
- Uses clear, engaging prose — never keyword-stuffed
- Structures information with logical heading hierarchy
- Includes actionable information and concrete examples
- Responds in valid JSON matching the requested schema exactly

You never add generic filler, excessive introductions, or keyword repetition."""


class ContentGenAgent:
    """
    Generates full SEO content articles using competitor SERP analysis
    as a benchmark and Claude API for generation.
    """

    def __init__(self, project: Project) -> None:
        self.project = project
        self.claude = ClaudeClient()
        self.storage = StorageService()

    # ── Main entry point ───────────────────────────────────────────────────

    async def run(self, keyword_id: str) -> dict:
        logger.info("content_gen.start", keyword_id=keyword_id)

        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            keyword = await session.get(Keyword, keyword_id)
            if not keyword:
                raise ValueError(f"Keyword {keyword_id} not found")

            # Get SERP snapshots for this keyword (top 5)
            result = await session.execute(
                select(SerpSnapshot)
                .where(SerpSnapshot.keyword_id == keyword_id)
                .order_by(SerpSnapshot.position)
                .limit(5)
            )
            serp_snapshots = result.scalars().all()

        # Build competitive brief
        brief = self._build_brief(keyword, serp_snapshots)

        # Generate content via Claude
        content = await self._generate_content(keyword, brief)

        # Score content quality
        semantic_score = self._score_semantic_coverage(content, brief)

        # Save to S3
        s3_key = await self._save_to_storage(content, keyword)

        # Create ContentVersion record
        version_id = await self._create_content_version(
            keyword=keyword,
            content=content,
            s3_key=s3_key,
            semantic_score=semantic_score,
        )

        logger.info(
            "content_gen.complete",
            keyword=keyword.query,
            word_count=content.get("word_count", 0),
            semantic_score=semantic_score,
        )
        return {
            "content_version_id": str(version_id),
            "keyword": keyword.query,
            "word_count": content.get("word_count", 0),
            "semantic_score": semantic_score,
            "s3_key": s3_key,
        }

    # ── Brief building ─────────────────────────────────────────────────────

    def _build_brief(self, keyword: Keyword, snapshots: list[SerpSnapshot]) -> dict:
        avg_word_count = (
            sum(s.word_count or 0 for s in snapshots) // max(len(snapshots), 1)
        )
        target_word_count = max(avg_word_count + 200, settings.content_min_words)

        all_h2s = list({h for s in snapshots for h in (s.h2_headings or [])})
        all_entities = list({e for s in snapshots for e in (s.entities or [])})
        all_paa = list({q for s in snapshots for q in (s.paa_questions or [])})
        schema_types = list({t for s in snapshots for t in (s.schema_types or [])})
        has_featured_snippet = any(s.has_featured_snippet for s in snapshots)

        return {
            "target_keyword": keyword.query,
            "search_intent": keyword.search_intent,
            "cluster_label": keyword.cluster_label,
            "target_word_count": min(target_word_count, settings.content_max_words),
            "competitor_h2s": all_h2s[:20],
            "required_entities": all_entities[:25],
            "paa_questions": all_paa[:8],
            "schema_types_in_use": schema_types,
            "has_featured_snippet_opportunity": has_featured_snippet,
            "brand_voice": self.project.brand_voice or "professional, helpful, clear",
            "target_audience": self.project.target_audience or "general audience",
            "language": self.project.content_language,
        }

    # ── Content generation ─────────────────────────────────────────────────

    async def _generate_content(self, keyword: Keyword, brief: dict) -> dict:
        prompt = self._build_prompt(brief)

        response_text = await self.claude.complete(
            system=SYSTEM_PROMPT,
            user=prompt,
            max_tokens=settings.anthropic_max_tokens,
        )

        # Parse JSON response
        try:
            content = json.loads(response_text)
        except json.JSONDecodeError:
            # Attempt to extract JSON from markdown code block
            match = re.search(r"```json\s*([\s\S]+?)\s*```", response_text)
            if match:
                content = json.loads(match.group(1))
            else:
                raise ValueError("Claude response was not valid JSON")

        # Compute word count
        full_text = " ".join([
            content.get("title", ""),
            content.get("meta_description", ""),
            *[s.get("content", "") for s in content.get("sections", [])],
        ])
        content["word_count"] = len(full_text.split())

        return content

    def _build_prompt(self, brief: dict) -> str:
        return f"""Create a comprehensive, SEO-optimised article for the target keyword.

TARGET KEYWORD: {brief["target_keyword"]}
SEARCH INTENT: {brief["search_intent"]}
TARGET WORD COUNT: {brief["target_word_count"]} words
BRAND VOICE: {brief["brand_voice"]}
TARGET AUDIENCE: {brief["target_audience"]}

COMPETITIVE INTELLIGENCE (from top-ranking pages):
- Competitor H2 headings (use as topic coverage guide, not copy): {json.dumps(brief["competitor_h2s"][:10])}
- Required entities to cover: {json.dumps(brief["required_entities"][:15])}
- People Also Ask questions to answer: {json.dumps(brief["paa_questions"])}
- Schema types used by competitors: {json.dumps(brief["schema_types_in_use"])}
{"- Opportunity: write a concise definition/answer for a featured snippet" if brief["has_featured_snippet_opportunity"] else ""}

INSTRUCTIONS:
1. Create original content — do not copy competitor structure directly
2. Ensure ALL required entities appear naturally in the content
3. Answer all PAA questions within relevant sections
4. {"Include an FAQ section with the PAA questions as a FAQPage schema" if brief["paa_questions"] else ""}
5. Write at least {brief["target_word_count"]} words of body content

Respond with ONLY valid JSON (no markdown fences) matching this exact schema:
{{
  "title": "string (50-60 chars, includes target keyword)",
  "meta_description": "string (140-160 chars, includes keyword, has CTA)",
  "slug": "string (URL-friendly, keyword-based)",
  "h1": "string (can differ slightly from title)",
  "sections": [
    {{
      "heading": "string (H2 text)",
      "heading_level": 2,
      "content": "string (HTML paragraph content for this section)",
      "subsections": [
        {{
          "heading": "string (H3 text)",
          "content": "string"
        }}
      ]
    }}
  ],
  "faq": [
    {{"question": "string", "answer": "string"}}
  ],
  "schema_suggestions": ["Article", "FAQPage"],
  "internal_link_suggestions": ["string (anchor text)"],
  "secondary_keywords": ["string"]
}}"""

    # ── Quality scoring ────────────────────────────────────────────────────

    def _score_semantic_coverage(self, content: dict, brief: dict) -> float:
        """Score 0-100: how many required entities and PAA questions are covered."""
        full_text = json.dumps(content).lower()
        required = brief.get("required_entities", []) + brief.get("paa_questions", [])
        if not required:
            return 75.0
        covered = sum(1 for r in required if r.lower() in full_text)
        return round((covered / len(required)) * 100, 1)

    # ── Storage ────────────────────────────────────────────────────────────

    async def _save_to_storage(self, content: dict, keyword: Keyword) -> str:
        slug = content.get("slug", keyword.query.lower().replace(" ", "-"))
        s3_key = f"projects/{self.project.id}/content/{slug}-{uuid.uuid4().hex[:8]}.json"
        await self.storage.put_json(s3_key, content)
        return s3_key

    async def _create_content_version(
        self,
        keyword: Keyword,
        content: dict,
        s3_key: str,
        semantic_score: float,
    ) -> uuid.UUID:
        SessionLocal = create_worker_session_factory()
        async with SessionLocal() as session:
            version = ContentVersion(
                project_id=self.project.id,
                keyword_id=keyword.id,
                status=ContentStatus.draft,
                content_type="article",
                title=content.get("title"),
                meta_description=content.get("meta_description"),
                slug=content.get("slug"),
                target_keyword=keyword.query,
                secondary_keywords=content.get("secondary_keywords", []),
                s3_key=s3_key,
                word_count=content.get("word_count", 0),
                semantic_score=semantic_score,
                generated_by="content_gen_agent",
                prompt_version="v1.0",
                generation_meta={"model": settings.anthropic_model},
            )
            session.add(version)
            await session.commit()
            await session.refresh(version)
            return version.id

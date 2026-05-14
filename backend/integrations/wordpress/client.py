"""
WordPress REST API Client
==========================
Publishes SEO-generated content to WordPress using Application Passwords.
Handles post creation, updating, and media upload.
"""
from __future__ import annotations

import base64
import json
from typing import Optional

import httpx

from core.logging import get_logger
from db.models import ContentVersion, Project

logger = get_logger("wordpress_client")


class WordPressClient:
    def __init__(self, project: Project) -> None:
        if not project.wp_base_url or not project.wp_username or not project.wp_app_password:
            raise ValueError("WordPress credentials not configured for this project")

        self.base_url = project.wp_base_url.rstrip("/")
        self.api_base = f"{self.base_url}/wp-json/wp/v2"
        credentials = f"{project.wp_username}:{project.wp_app_password}"
        self.auth_header = base64.b64encode(credentials.encode()).decode()
        self.headers = {
            "Authorization": f"Basic {self.auth_header}",
            "Content-Type": "application/json",
        }

    # ── Post operations ────────────────────────────────────────────────────

    async def create_post(
        self,
        title: str,
        content: str,
        slug: str,
        excerpt: str = "",
        status: str = "draft",
        meta_description: str = "",
        categories: Optional[list[int]] = None,
        tags: Optional[list[int]] = None,
        schema_json: Optional[dict] = None,
    ) -> dict:
        """Create a new WordPress post. Returns the created post data."""
        body: dict = {
            "title": title,
            "content": content,
            "slug": slug,
            "excerpt": excerpt,
            "status": status,
            "categories": categories or [],
            "tags": tags or [],
        }

        # Inject meta description via Yoast/RankMath if schema_json passed
        if meta_description:
            body["meta"] = {
                "_yoast_wpseo_metadesc": meta_description,
                "rank_math_description": meta_description,
            }

        if schema_json:
            # Inject JSON-LD via custom field
            body.setdefault("meta", {})
            body["meta"]["_custom_schema"] = json.dumps(schema_json)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_base}/posts",
                json=body,
                headers=self.headers,
            )

        if resp.status_code not in (200, 201):
            logger.error("wp.create_post_error", status=resp.status_code, body=resp.text[:500])
            raise RuntimeError(f"WordPress post creation failed: {resp.status_code}")

        post_data = resp.json()
        logger.info("wp.post_created", post_id=post_data["id"], slug=slug)
        return post_data

    async def update_post(
        self,
        post_id: int,
        updates: dict,
    ) -> dict:
        """Update an existing WordPress post."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.put(
                f"{self.api_base}/posts/{post_id}",
                json=updates,
                headers=self.headers,
            )

        if resp.status_code != 200:
            logger.error("wp.update_post_error", post_id=post_id, status=resp.status_code)
            raise RuntimeError(f"WordPress post update failed: {resp.status_code}")

        logger.info("wp.post_updated", post_id=post_id)
        return resp.json()

    async def get_post_by_slug(self, slug: str) -> Optional[dict]:
        """Find a post by its slug."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.api_base}/posts",
                params={"slug": slug, "per_page": 1},
                headers=self.headers,
            )
        posts = resp.json()
        return posts[0] if posts else None

    # ── Content version publishing ─────────────────────────────────────────

    async def publish_content_version(
        self,
        version: ContentVersion,
        content_data: dict,
        status: str = "draft",
    ) -> dict:
        """
        Publish a ContentVersion to WordPress.
        content_data is the parsed JSON from S3.
        """
        # Build HTML body from sections
        html_body = self._build_html(content_data)

        # Build FAQ schema if present
        schema = self._build_faq_schema(content_data) if content_data.get("faq") else None

        # Check if post already exists
        existing = await self.get_post_by_slug(version.slug or "")

        if existing:
            post = await self.update_post(existing["id"], {
                "title": version.title,
                "content": html_body,
                "excerpt": version.meta_description or "",
                "status": status,
                "meta": {"_yoast_wpseo_metadesc": version.meta_description or ""},
            })
        else:
            post = await self.create_post(
                title=version.title or "",
                content=html_body,
                slug=version.slug or "",
                excerpt=version.meta_description or "",
                meta_description=version.meta_description or "",
                status=status,
                schema_json=schema,
            )

        return {
            "wp_post_id": post["id"],
            "wp_post_url": post.get("link", ""),
            "status": post.get("status", "draft"),
        }

    # ── Helpers ────────────────────────────────────────────────────────────

    def _build_html(self, content: dict) -> str:
        """Convert structured content JSON to WordPress HTML."""
        parts: list[str] = []

        for section in content.get("sections", []):
            level = section.get("heading_level", 2)
            parts.append(f"<h{level}>{section['heading']}</h{level}>")
            parts.append(f"<p>{section.get('content', '')}</p>")
            for sub in section.get("subsections", []):
                parts.append(f"<h3>{sub['heading']}</h3>")
                parts.append(f"<p>{sub.get('content', '')}</p>")

        # FAQ section
        faq = content.get("faq", [])
        if faq:
            parts.append("<h2>Frequently Asked Questions</h2>")
            parts.append('<div class="faq-section">')
            for item in faq:
                parts.append(f"<h3>{item['question']}</h3>")
                parts.append(f"<p>{item['answer']}</p>")
            parts.append("</div>")

        return "\n".join(parts)

    def _build_faq_schema(self, content: dict) -> dict:
        """Build FAQPage JSON-LD schema from FAQ items."""
        faq_items = content.get("faq", [])
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": item["question"],
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": item["answer"],
                    },
                }
                for item in faq_items
            ],
        }

    async def test_connection(self) -> bool:
        """Verify WordPress credentials are valid."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.api_base}/users/me",
                    headers=self.headers,
                )
            return resp.status_code == 200
        except Exception:
            return False

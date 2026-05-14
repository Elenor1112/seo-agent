"""
Serper.dev SERP API Client
===========================
Drop-in replacement for DataForSEOClient.
Fetches organic SERP results with caching (24h TTL in Redis).
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

import httpx
import redis.asyncio as aioredis

from core.config import settings
from core.logging import get_logger

logger = get_logger("serper_client")

CACHE_TTL = 86400  # 24 hours


class DataForSEOClient:
    """Named DataForSEOClient to avoid changing any imports elsewhere."""

    def __init__(self) -> None:
        self.base_url = "https://google.serper.dev"
        self.api_key = settings.serper_api_key
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if not self._redis:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    def _cache_key(self, query: str, location_code: int, language_code: str) -> str:
        raw = f"serp:{query}:{location_code}:{language_code}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def organic_search(
        self,
        query: str,
        location_code: int = 2840,
        language_code: str = "en",
        depth: int = 10,
    ) -> dict:
        """
        Fetch organic SERP results. Returns cached result if available.
        location_code 2840 = United States (mapped to gl/hl for Serper).
        """
        cache_key = self._cache_key(query, location_code, language_code)
        redis = await self._get_redis()

        cached = await redis.get(cache_key)
        if cached:
            logger.debug("serp.cache_hit", query=query)
            return json.loads(cached)

        result = await self._call_api(query, location_code, language_code, depth)

        await redis.setex(cache_key, CACHE_TTL, json.dumps(result))
        return result

    async def _call_api(
        self,
        query: str,
        location_code: int,
        language_code: str,
        depth: int,
    ) -> dict:
        # Map DataForSEO location_code → Serper gl (country code)
        # Extend this dict as needed for other markets
        location_map = {
            2840: "us",  # United States
            2826: "gb",  # United Kingdom
            2036: "au",  # Australia
            2124: "ca",  # Canada
            2818: "eg",  # Egypt
        }
        gl = location_map.get(location_code, "us")

        payload = {
            "q": query,
            "gl": gl,
            "hl": language_code,
            "num": depth,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/search",
                json=payload,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code != 200:
            logger.error("serper.api_error", status=resp.status_code, query=query)
            return {"organic_results": [], "related_questions": []}

        data = resp.json()

        organic = []
        for i, item in enumerate(data.get("organic", []), start=1):
            organic.append({
                "rank_absolute": item.get("position", i),
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "description": item.get("snippet", ""),
                "domain": item.get("displayLink", ""),
                "featured_snippet": "answerBox" in data and i == 1,
            })

        paa = []
        for item in data.get("peopleAlsoAsk", []):
            if q := item.get("question"):
                paa.append({"question": q})

        logger.info("serper.fetched", query=query, organic=len(organic), paa=len(paa))
        return {"organic_results": organic, "related_questions": paa}
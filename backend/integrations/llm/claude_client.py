"""
LLM Client — OpenRouter
========================
Drop-in replacement for the Anthropic client.
OpenRouter uses OpenAI-compatible API format.
"""
from __future__ import annotations
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from core.config import settings
from core.logging import get_logger

logger = get_logger("llm_client")


class ClaudeClient:  # keep class name — all agents import this
    def __init__(self) -> None:
        self.api_key = settings.anthropic_api_key  # we reuse this setting for the OpenRouter key
        self.model = "inclusionai/ring-2.6-1t:free"
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        reraise=True,
    )
    async def complete(
        self,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",   # required by OpenRouter
            "X-Title": "SEO Agent",                    # shows in OpenRouter dashboard
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(self.base_url, json=payload, headers=headers)

        if resp.status_code != 200:
            logger.error("openrouter.error", status=resp.status_code, body=resp.text[:500])
            raise RuntimeError(f"OpenRouter API error: {resp.status_code} — {resp.text[:300]}")

        data = resp.json()
        text = data["choices"][0]["message"]["content"]

        logger.info(
            "llm.response",
            model=self.model,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
        )

        return text

    async def complete_with_schema_retry(
        self,
        user: str,
        system: Optional[str] = None,
        max_tokens: int = 8192,
        max_retries: int = 2,
    ) -> str:
        """Retry if response is not valid JSON — used by content gen and optimizer."""
        import json, re

        for attempt in range(max_retries + 1):
            text = await self.complete(user=user, system=system, max_tokens=max_tokens)
            try:
                json.loads(text)
                return text
            except json.JSONDecodeError:
                match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
                if match:
                    try:
                        json.loads(match.group(1))
                        return match.group(1)
                    except json.JSONDecodeError:
                        pass
                if attempt < max_retries:
                    logger.warning("llm.invalid_json_retry", attempt=attempt + 1)
                    user = (
                        f"{user}\n\nYour previous response was not valid JSON. "
                        f"Respond with ONLY the JSON object, no markdown, no explanation."
                    )
                else:
                    raise ValueError(f"LLM failed to return valid JSON after {max_retries + 1} attempts")
        return ""
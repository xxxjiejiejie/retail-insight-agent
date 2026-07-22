from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, IntegrationError, LLMResponseError


@dataclass(slots=True, frozen=True)
class LLMTextResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    model: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class TextGenerator(Protocol):
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse: ...


class DeepSeekAnthropicClient:
    """Small Anthropic-compatible client for DeepSeek without SDK lock-in."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._transport = transport

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        if not self._settings.llm_api_key:
            raise ConfigurationError("尚未在 .env 中配置 LLM_API_KEY")

        endpoint = f"{self._settings.llm_base_url.rstrip('/')}/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self._settings.llm_api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self._settings.llm_model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(60.0, connect=15.0),
            ) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise IntegrationError(f"DeepSeek API 返回 HTTP {status}") from exc
        except httpx.HTTPError as exc:
            raise IntegrationError("无法连接 DeepSeek API") from exc

        try:
            body: dict[str, Any] = response.json()
            content_blocks = body.get("content", [])
            text_parts = [
                block.get("text", "")
                for block in content_blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = "".join(text_parts).strip()
            usage = body.get("usage", {})
            if not content:
                raise ValueError("empty content")
            return LLMTextResponse(
                content=content,
                prompt_tokens=int(usage.get("input_tokens", 0)),
                completion_tokens=int(usage.get("output_tokens", 0)),
                latency_ms=round((perf_counter() - started) * 1000, 2),
                model=str(body.get("model") or self._settings.llm_model),
            )
        except (TypeError, ValueError) as exc:
            raise LLMResponseError("DeepSeek API 返回了无法解析的响应") from exc


@lru_cache
def get_llm_client() -> DeepSeekAnthropicClient:
    return DeepSeekAnthropicClient(get_settings())

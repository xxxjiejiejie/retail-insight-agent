from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import Any, Protocol

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, IntegrationError, LLMResponseError
from app.observability.langsmith import observe_llm
from app.tools.models import ToolCall, ToolDefinition


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


@dataclass(slots=True, frozen=True)
class LLMToolResponse:
    text: str
    tool_calls: tuple[ToolCall, ...]
    content_blocks: tuple[dict[str, Any], ...]
    stop_reason: str = ""
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


class ToolGenerator(Protocol):
    async def generate_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        max_tokens: int = 1_600,
    ) -> LLMToolResponse: ...


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
        async with observe_llm(
            system=system,
            user=user,
            model=self._settings.llm_model,
            max_tokens=max_tokens,
        ) as span:
            result = await self._generate_text(
                system=system,
                user=user,
                max_tokens=max_tokens,
            )
            await span.end(
                content=result.content,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
            )
            return result

    async def generate_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        max_tokens: int = 1_600,
    ) -> LLMToolResponse:
        trace_summary = (
            f"[tool-agent messages omitted] message_count={len(messages)}; "
            f"tools={','.join(tool.name for tool in tools)}"
        )
        async with observe_llm(
            system=system,
            user=trace_summary,
            model=self._settings.llm_model,
            max_tokens=max_tokens,
        ) as span:
            result = await self._generate_with_tools(
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=max_tokens,
            )
            span_content = result.text or "[tool_use] " + ",".join(
                call.name for call in result.tool_calls
            )
            await span.end(
                content=span_content,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                latency_ms=result.latency_ms,
            )
            return result

    async def _post_messages(self, payload: dict[str, Any]) -> tuple[dict[str, Any], float]:
        if not self._settings.llm_api_key:
            raise ConfigurationError("尚未在 .env 中配置 LLM_API_KEY")

        endpoint = f"{self._settings.llm_base_url.rstrip('/')}/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self._settings.llm_api_key,
            "anthropic-version": "2023-06-01",
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
        except httpx.TimeoutException as exc:
            raise IntegrationError("DeepSeek API 请求超时") from exc
        except httpx.HTTPError as exc:
            raise IntegrationError("无法连接 DeepSeek API") from exc
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("response body must be an object")
            return body, round((perf_counter() - started) * 1000, 2)
        except (TypeError, ValueError) as exc:
            raise LLMResponseError("DeepSeek API 返回了无法解析的响应") from exc

    async def _generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
    ) -> LLMTextResponse:
        payload = {
            "model": self._settings.llm_model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        body, latency_ms = await self._post_messages(payload)

        try:
            content_blocks = body.get("content", [])
            text_parts: list[str] = []
            if isinstance(content_blocks, str):
                text_parts.append(content_blocks)
            elif isinstance(content_blocks, list):
                text_parts.extend(
                    str(block.get("text", ""))
                    for block in content_blocks
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            choices = body.get("choices")
            if not text_parts and isinstance(choices, list) and choices:
                first_choice = choices[0]
                if isinstance(first_choice, dict):
                    message = first_choice.get("message")
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        text_parts.append(message["content"])
            content = "".join(text_parts).strip()
            usage = body.get("usage", {})
            if not content:
                raise ValueError("empty content")
            return LLMTextResponse(
                content=content,
                prompt_tokens=int(usage.get("input_tokens", usage.get("prompt_tokens", 0))),
                completion_tokens=int(
                    usage.get("output_tokens", usage.get("completion_tokens", 0))
                ),
                latency_ms=latency_ms,
                model=str(body.get("model") or self._settings.llm_model),
            )
        except (TypeError, ValueError) as exc:
            raise LLMResponseError("DeepSeek API 返回了无法解析的响应") from exc

    async def _generate_with_tools(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        max_tokens: int,
    ) -> LLMToolResponse:
        payload = {
            "model": self._settings.llm_model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "system": system,
            "messages": messages,
            "tools": [tool.model_dump() for tool in tools],
        }
        body, latency_ms = await self._post_messages(payload)
        try:
            blocks = body.get("content", [])
            if isinstance(blocks, str):
                blocks = [{"type": "text", "text": blocks}]
            if not isinstance(blocks, list):
                raise TypeError("content must be a list")

            normalized_blocks: list[dict[str, Any]] = []
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                    normalized_blocks.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    arguments = block.get("input", {})
                    if not isinstance(arguments, dict):
                        raise TypeError("tool input must be an object")
                    call = ToolCall(
                        id=str(block.get("id", "")),
                        name=str(block.get("name", "")),
                        arguments=arguments,
                    )
                    tool_calls.append(call)
                    normalized_blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": call.arguments,
                        }
                    )

            choices = body.get("choices")
            if not normalized_blocks and isinstance(choices, list) and choices:
                first = choices[0]
                message = first.get("message", {}) if isinstance(first, dict) else {}
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        text_parts.append(content)
                        normalized_blocks.append({"type": "text", "text": content})
                    raw_calls = message.get("tool_calls", [])
                    if isinstance(raw_calls, list):
                        for raw_call in raw_calls:
                            if not isinstance(raw_call, dict):
                                continue
                            function = raw_call.get("function", {})
                            if not isinstance(function, dict):
                                continue
                            raw_arguments = function.get("arguments", "{}")
                            arguments = (
                                json.loads(raw_arguments)
                                if isinstance(raw_arguments, str)
                                else raw_arguments
                            )
                            if not isinstance(arguments, dict):
                                raise TypeError("tool arguments must be an object")
                            call = ToolCall(
                                id=str(raw_call.get("id", "")),
                                name=str(function.get("name", "")),
                                arguments=arguments,
                            )
                            tool_calls.append(call)
                            normalized_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": call.id,
                                    "name": call.name,
                                    "input": call.arguments,
                                }
                            )
            if not normalized_blocks:
                raise ValueError("empty content")
            usage = body.get("usage", {})
            if not isinstance(usage, dict):
                usage = {}
            stop_reason = str(body.get("stop_reason") or "")
            if not stop_reason and isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    stop_reason = str(first.get("finish_reason") or "")
            return LLMToolResponse(
                text="".join(text_parts).strip(),
                tool_calls=tuple(tool_calls),
                content_blocks=tuple(normalized_blocks),
                stop_reason=stop_reason,
                prompt_tokens=int(usage.get("input_tokens", usage.get("prompt_tokens", 0))),
                completion_tokens=int(
                    usage.get("output_tokens", usage.get("completion_tokens", 0))
                ),
                latency_ms=latency_ms,
                model=str(body.get("model") or self._settings.llm_model),
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise LLMResponseError("DeepSeek API 返回了无法解析的工具调用响应") from exc


@lru_cache
def get_llm_client() -> DeepSeekAnthropicClient:
    return DeepSeekAnthropicClient(get_settings())

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.callbacks.manager import (
    AsyncCallbackManager,
    AsyncCallbackManagerForChainRun,
    AsyncCallbackManagerForLLMRun,
)
from langchain_core.outputs import Generation, LLMResult
from langchain_core.tracers.context import tracing_v2_enabled
from langchain_core.tracers.langchain import LangChainTracer
from langsmith import Client

from app.core.config import get_settings

REDACTED = "[REDACTED]"
SECRET_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "cookies",
    "database_url",
    "headers",
    "langsmith_api_key",
    "llm_api_key",
    "password",
    "set_cookie",
    "x_api_key",
}
CONTENT_KEYS = {
    "content",
    "context",
    "contexts",
    "excerpt",
    "page_content",
    "policy_excerpt",
    "retrieved_docs",
}
KEY_PATTERN = re.compile(r"(?i)(?:lsv2_[a-z0-9_\-]{16,}|sk-[a-z0-9_\-]{16,})")
URL_CREDENTIAL_PATTERN = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@", re.I)


def _normalized_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def _is_secret_key(key: str) -> bool:
    return (
        key in SECRET_KEYS
        or key.endswith("_api_key")
        or key.endswith("_password")
        or key.endswith("_secret")
    )


def _safe_text(value: str, *, limit: int) -> str:
    cleaned = KEY_PATTERN.sub(REDACTED, value)
    cleaned = URL_CREDENTIAL_PATTERN.sub(r"\g<scheme>[REDACTED]@", cleaned)
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}…[TRUNCATED {len(cleaned) - limit} chars]"


def _sanitize(value: Any, *, key: str = "", depth: int = 0) -> Any:
    settings = get_settings()
    if depth > 12:
        return "[MAX_DEPTH]"
    if _is_secret_key(key):
        return REDACTED
    if key == "rows" and isinstance(value, Sequence) and not isinstance(value, str):
        return {"omitted": True, "row_count": len(value)}
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize(
                item_value,
                key=_normalized_key(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize(item, key=key, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        limit = (
            settings.langsmith_policy_excerpt_length
            if key in CONTENT_KEYS
            else settings.langsmith_max_string_length
        )
        return _safe_text(value, limit=limit)
    if isinstance(value, bytes):
        return f"[BINARY {len(value)} bytes]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _safe_text(str(value), limit=settings.langsmith_max_string_length)


def sanitize_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove secrets and result rows before a payload leaves the application."""

    sanitized = _sanitize(payload)
    return sanitized if isinstance(sanitized, dict) else {"value": sanitized}


@lru_cache
def get_langsmith_client() -> Client:
    settings = get_settings()
    return Client(
        api_url=settings.langsmith_endpoint,
        api_key=settings.langsmith_api_key,
        hide_inputs=sanitize_trace_payload,
        hide_outputs=sanitize_trace_payload,
        hide_metadata=sanitize_trace_payload,
        omit_traced_runtime_info=True,
    )


def _trace_metadata(session_id: str, query: str) -> dict[str, Any]:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "environment": settings.app_env,
        "session_id": session_id,
        "query_length": len(query),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "data_as_of_date": settings.data_as_of_date.isoformat(),
        "privacy": "rows-omitted;secrets-redacted;documents-truncated",
    }


@contextmanager
def trace_agent_request(
    *,
    session_id: str,
    query: str,
    config: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], LangChainTracer | None]]:
    """Attach a redacting LangSmith tracer to one LangGraph request."""

    settings = get_settings()
    if not settings.langsmith_enabled:
        yield config, None
        return

    client = get_langsmith_client()
    tags = [settings.app_env, "retail-insight-agent", "langgraph"]
    metadata = _trace_metadata(session_id, query)
    with tracing_v2_enabled(
        project_name=settings.langsmith_project,
        tags=tags,
        client=client,
    ) as tracer:
        traced_config = {
            **config,
            "callbacks": [tracer],
            "metadata": metadata,
            "tags": tags,
            "run_name": "retail-insight.request",
        }
        yield traced_config, tracer


@dataclass(slots=True)
class ChainSpan:
    manager: AsyncCallbackManagerForChainRun | None
    ended: bool = False

    async def end(self, outputs: dict[str, Any]) -> None:
        if self.manager is not None and not self.ended:
            await self.manager.on_chain_end(sanitize_trace_payload(outputs))
            self.ended = True


@asynccontextmanager
async def observe_chain(
    name: str,
    *,
    inputs: dict[str, Any],
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[ChainSpan]:
    """Create a nested operation span when the request tracer is active."""

    if not get_settings().langsmith_enabled:
        yield ChainSpan(None)
        return
    callback_manager = AsyncCallbackManager.configure(
        inheritable_tags=tags or [],
        inheritable_metadata=sanitize_trace_payload(metadata or {}),
    )
    run_manager = await callback_manager.on_chain_start(
        {"name": name},
        sanitize_trace_payload(inputs),
        name=name,
    )
    span = ChainSpan(run_manager)
    try:
        yield span
    except BaseException as exc:
        await run_manager.on_chain_error(exc)
        span.ended = True
        raise
    finally:
        if not span.ended:
            await span.end({})


@dataclass(slots=True)
class LLMSpan:
    manager: AsyncCallbackManagerForLLMRun | None
    ended: bool = False

    async def end(
        self,
        *,
        content: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
    ) -> None:
        if self.manager is None or self.ended:
            return
        result = LLMResult(
            generations=[[Generation(text=content)]],
            llm_output={
                "model": model,
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "latency_ms": latency_ms,
            },
        )
        await self.manager.on_llm_end(result)
        self.ended = True


@asynccontextmanager
async def observe_llm(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
) -> AsyncIterator[LLMSpan]:
    """Create a native LangSmith LLM span without exposing headers or API keys."""

    if not get_settings().langsmith_enabled:
        yield LLMSpan(None)
        return
    callback_manager = AsyncCallbackManager.configure(
        inheritable_tags=["deepseek", "llm"],
        inheritable_metadata={"model": model, "max_tokens": max_tokens},
    )
    prompt = _safe_text(
        f"[SYSTEM]\n{system}\n\n[USER]\n{user}",
        limit=get_settings().langsmith_max_string_length,
    )
    managers = await callback_manager.on_llm_start(
        {
            "name": "DeepSeekAnthropicClient",
            "id": ["app", "llm", "DeepSeekAnthropicClient"],
        },
        [prompt],
        name="deepseek.generate_text",
        invocation_params={"model": model, "max_tokens": max_tokens, "temperature": 0},
    )
    span = LLMSpan(managers[0] if managers else None)
    try:
        yield span
    except BaseException as exc:
        if span.manager is not None:
            await span.manager.on_llm_error(exc)
        span.ended = True
        raise

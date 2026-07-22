"""Run one minimal DeepSeek request without printing credentials or response text."""

from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.llm.deepseek import get_llm_client


async def main() -> None:
    settings = get_settings()
    if not settings.llm_api_key:
        raise SystemExit("LLM_API_KEY is not configured in .env")

    response = await get_llm_client().generate_text(
        system="你是 API 连通性检查器，只输出 JSON。",
        user='只输出 {"status":"ok"}，不要添加其他文字。',
        max_tokens=64,
    )
    try:
        payload = json.loads(response.content)
        content_valid = payload.get("status") == "ok"
    except (json.JSONDecodeError, AttributeError):
        content_valid = False

    print(f"connected=true model={response.model or settings.llm_model}")
    print(f"content_valid={str(content_valid).lower()}")
    print(
        f"prompt_tokens={response.prompt_tokens} "
        f"completion_tokens={response.completion_tokens} "
        f"latency_ms={response.latency_ms}"
    )
    if not content_valid:
        raise SystemExit("DeepSeek returned an unexpected response format")


if __name__ == "__main__":
    asyncio.run(main())

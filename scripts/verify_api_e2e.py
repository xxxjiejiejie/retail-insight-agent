"""Exercise one real Hybrid request through the FastAPI ASGI interface."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.database.engine import get_business_engine
from app.main import app


async def main() -> None:
    query = (
        "2026年6月哪些门店没有完成销售目标？"
        "并说明销售目标完成率在绩效中的权重和数据确认规则。"
    )
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat",
                json={"query": query, "session_id": "hybrid-e2e-check"},
                timeout=120,
            )
    finally:
        if get_business_engine.cache_info().currsize:
            await get_business_engine().dispose()
            get_business_engine.cache_clear()
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    safe_payload = {
        "status_code": response.status_code,
        "intent": payload.get("intent"),
        "answer": payload.get("answer"),
        "generated_sql": payload.get("generated_sql"),
        "row_count": (payload.get("sql_result") or {}).get("row_count"),
        "citation_document_ids": [
            citation.get("document_id") for citation in payload.get("citations", [])
        ],
        "errors": payload.get("errors", []),
        "metrics": payload.get("metrics", {}),
    }
    print(json.dumps(safe_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

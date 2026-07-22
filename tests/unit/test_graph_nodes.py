import pytest

from app.graph import nodes


@pytest.mark.asyncio
async def test_sql_node_preserves_service_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_handler(_: str) -> dict:
        return {"answer": "ok", "metrics": {"total_tokens": 42, "attempt_count": 1}}

    monkeypatch.setattr(nodes, "handle_sql_question", fake_handler)
    result = await nodes.sql_node({"user_query": "各区域门店数"})

    assert result["metrics"]["total_tokens"] == 42
    assert result["metrics"]["attempt_count"] == 1
    assert result["metrics"]["sql_branch_ms"] >= 0

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


def test_merge_hybrid_metrics_sums_tokens_and_preserves_rag_metrics() -> None:
    result = nodes.merge_hybrid_metrics(
        {"total_tokens": 100, "llm_latency_ms": 20.0, "sql_execution_ms": 3.0},
        {"total_tokens": 40, "llm_latency_ms": 8.0, "retrieval_ms": 2.0},
        total_ms=35.0,
    )

    assert result["total_tokens"] == 140
    assert result["llm_latency_ms"] == 28.0
    assert result["sql_execution_ms"] == 3.0
    assert result["retrieval_ms"] == 2.0
    assert result["total_latency_ms"] == 35.0

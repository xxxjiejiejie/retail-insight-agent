import pytest

from app.graph import nodes
from app.graph.state import merge_turns


@pytest.mark.asyncio
async def test_sql_node_preserves_service_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_handler(_: str) -> dict:
        return {"answer": "ok", "metrics": {"total_tokens": 42, "attempt_count": 1}}

    monkeypatch.setattr(nodes, "handle_sql_question", fake_handler)
    result = await nodes.sql_node({"user_query": "各区域门店数"})

    assert result["metrics"]["total_tokens"] == 42
    assert result["metrics"]["attempt_count"] == 1
    assert result["metrics"]["sql_branch_ms"] >= 0
    assert result["metrics"]["context_used"] is False


@pytest.mark.asyncio
async def test_sql_node_uses_resolved_context_query(monkeypatch: pytest.MonkeyPatch) -> None:
    received = ""

    async def fake_handler(query: str) -> dict:
        nonlocal received
        received = query
        return {"answer": "ok", "metrics": {}}

    monkeypatch.setattr(nodes, "handle_sql_question", fake_handler)
    result = await nodes.sql_node(
        {
            "user_query": "那华东呢",
            "resolved_query": "第二季度各区域销售额；基于上一问题继续追问：那华东呢",
            "context_used": True,
        }
    )

    assert received.startswith("第二季度各区域销售额")
    assert result["metrics"]["context_used"] is True


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


def test_split_hybrid_query_separates_data_and_policy_questions() -> None:
    sql_query, rag_query = nodes.split_hybrid_query(
        "2026年6月哪些门店没有完成销售目标？并说明销售目标完成率在绩效中的权重"
    )

    assert sql_query == "2026年6月哪些门店没有完成销售目标"
    assert rag_query == "销售目标完成率在绩效中的权重"


def test_persist_turn_node_keeps_only_lightweight_history() -> None:
    result = nodes.persist_turn_node(
        {
            "user_query": "你好",
            "intent": "general",
            "answer": "你好，请问需要分析什么？",
            "sql_result": {"rows": [{"large": "payload"}]},
            "citations": [],
            "errors": [],
            "metrics": {"total_tokens": 0},
        }
    )

    turn = result["turns"][0]
    assert turn["query"] == "你好"
    assert turn["intent"] == "general"
    assert "sql_result" not in turn


def test_session_history_keeps_latest_twenty_turns() -> None:
    existing = [{"turn_id": str(index)} for index in range(19)]
    new = [{"turn_id": str(index)} for index in range(19, 25)]

    merged = merge_turns(existing, new)

    assert len(merged) == 20
    assert merged[0]["turn_id"] == "5"
    assert merged[-1]["turn_id"] == "24"


@pytest.mark.asyncio
async def test_hybrid_node_uses_separate_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    received: dict[str, str] = {}

    async def fake_sql_handler(query: str) -> dict:
        received["sql"] = query
        return {"answer": "数据回答", "errors": [], "metrics": {"total_tokens": 10}}

    async def fake_rag_handler(query: str) -> dict:
        received["rag"] = query
        return {"answer": "制度回答", "errors": [], "metrics": {"total_tokens": 20}}

    monkeypatch.setattr(nodes, "handle_sql_question", fake_sql_handler)
    monkeypatch.setattr(nodes, "handle_rag_question", fake_rag_handler)
    result = await nodes.hybrid_node(
        {
            "user_query": (
                "2026年6月哪些门店没有完成销售目标？"
                "并说明销售目标完成率在绩效中的权重"
            )
        }
    )

    assert received == {
        "sql": "2026年6月哪些门店没有完成销售目标",
        "rag": "销售目标完成率在绩效中的权重",
    }
    assert result["answer"] == "数据回答\n\n制度回答"
    assert result["metrics"]["total_tokens"] == 30

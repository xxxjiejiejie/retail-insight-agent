from __future__ import annotations

from app.graph.context import resolve_contextual_query
from app.graph.nodes import route_node


def analytical_turn(query: str, intent: str = "sql") -> dict[str, str]:
    return {"turn_id": "turn-1", "query": query, "intent": intent}


def test_does_not_resolve_without_prior_analytical_turn() -> None:
    resolution = resolve_contextual_query(
        "那华东呢",
        [analytical_turn("你好", intent="general")],
    )

    assert resolution.query == "那华东呢"
    assert resolution.used_context is False


def test_resolves_short_sql_followup_from_previous_turn() -> None:
    resolution = resolve_contextual_query(
        "那华东呢",
        [analytical_turn("2026年第二季度各区域销售额是多少？")],
    )

    assert resolution.used_context is True
    assert resolution.source_turn_id == "turn-1"
    assert "第二季度各区域销售额" in resolution.query
    assert "那华东呢" in resolution.query


def test_resolves_policy_followup_and_preserves_rag_intent() -> None:
    state = route_node(
        {
            "user_query": "这个制度的申诉期限呢",
            "turns": [analytical_turn("绩效结果有异议时如何申诉？", intent="rag")],
        }
    )

    assert state["context_used"] is True
    assert state["intent"] == "rag"
    assert "绩效结果" in state["resolved_query"]


def test_standalone_question_is_not_polluted_by_history() -> None:
    resolution = resolve_contextual_query(
        "2026年6月各门店销售额是多少？",
        [analytical_turn("2026年第一季度各区域订单数")],
    )

    assert resolution.query == "2026年6月各门店销售额是多少？"
    assert resolution.used_context is False

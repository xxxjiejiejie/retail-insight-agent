import asyncio
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from app.graph.context import resolve_contextual_query
from app.graph.router import classify_intent
from app.graph.state import AgentState
from app.rag.service import handle_rag_question
from app.sql_agent.service import handle_sql_question

HYBRID_SEPARATORS = ("并说明", "同时说明", "并依据", "并结合", "同时")


def merge_hybrid_metrics(
    sql_metrics: dict,
    rag_metrics: dict,
    *,
    total_ms: float,
) -> dict:
    merged = {**sql_metrics, **rag_metrics}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "attempt_count"):
        numeric_values: list[int | float] = []
        for metrics in (sql_metrics, rag_metrics):
            value: object = metrics.get(key)
            if isinstance(value, (int, float)):
                numeric_values.append(value)
        if numeric_values:
            merged[key] = sum(numeric_values)
    llm_latencies: list[int | float] = []
    for metrics in (sql_metrics, rag_metrics):
        value = metrics.get("llm_latency_ms")
        if isinstance(value, (int, float)):
            llm_latencies.append(value)
    if llm_latencies:
        merged["llm_latency_ms"] = round(sum(llm_latencies), 2)
    merged["total_latency_ms"] = round(total_ms, 2)
    merged["hybrid_branch_ms"] = round(total_ms, 2)
    return merged


def route_node(state: AgentState) -> dict:
    resolution = resolve_contextual_query(state["user_query"], state.get("turns"))
    return {
        "intent": classify_intent(resolution.query),
        "resolved_query": resolution.query,
        "context_used": resolution.used_context,
        "context_source_turn_id": resolution.source_turn_id,
    }


def effective_query(state: AgentState) -> str:
    return state.get("resolved_query") or state["user_query"]


def attach_context_metric(state: AgentState, result: dict) -> dict:
    metrics = result.setdefault("metrics", {})
    metrics["context_used"] = bool(state.get("context_used"))
    return result


def split_hybrid_query(query: str) -> tuple[str, str]:
    for separator in HYBRID_SEPARATORS:
        if separator in query:
            sql_query, rag_query = query.split(separator, maxsplit=1)
            cleaned_sql = sql_query.strip(" ，,。；;？?")
            cleaned_rag = rag_query.strip(" ，,。；;？?")
            if cleaned_sql and cleaned_rag:
                return cleaned_sql, cleaned_rag
    return query, query


def clarify_node(state: AgentState) -> dict:
    return {
        "clarification": "请补充时间范围、区域、指标或具体制度名称。",
        "answer": "你的问题信息不足。请补充时间范围、区域、指标或具体制度名称。",
    }


def general_node(state: AgentState) -> dict:
    return {
        "answer": (
            "当前助手主要处理零售经营数据分析和企业制度问答。"
            "你可以询问销售、订单、库存、退货，或促销审批、退换货流程等问题。"
        )
    }


async def sql_node(state: AgentState) -> dict:
    started = perf_counter()
    result = await handle_sql_question(effective_query(state))
    metrics = result.setdefault("metrics", {})
    metrics["sql_branch_ms"] = round((perf_counter() - started) * 1000, 2)
    return attach_context_metric(state, result)


async def rag_node(state: AgentState) -> dict:
    started = perf_counter()
    result = await handle_rag_question(effective_query(state))
    metrics = result.setdefault("metrics", {})
    metrics["rag_branch_ms"] = round((perf_counter() - started) * 1000, 2)
    return attach_context_metric(state, result)


async def hybrid_node(state: AgentState) -> dict:
    started = perf_counter()
    sql_query, rag_query = split_hybrid_query(effective_query(state))
    sql_result, rag_result = await asyncio.gather(
        handle_sql_question(sql_query),
        handle_rag_question(rag_query),
    )
    result = {
        "generated_sql": sql_result.get("generated_sql"),
        "sql_result": sql_result.get("sql_result"),
        "chart_spec": sql_result.get("chart_spec"),
        "retrieved_docs": rag_result.get("retrieved_docs", []),
        "citations": rag_result.get("citations", []),
        "answer": f"{sql_result['answer']}\n\n{rag_result['answer']}",
        "errors": [*sql_result.get("errors", []), *rag_result.get("errors", [])],
        "metrics": merge_hybrid_metrics(
            sql_result.get("metrics", {}),
            rag_result.get("metrics", {}),
            total_ms=(perf_counter() - started) * 1000,
        ),
    }
    return attach_context_metric(state, result)


def route_key(state: AgentState) -> str:
    return state["intent"]


def persist_turn_node(state: AgentState) -> dict:
    """Append a compact, JSON-serializable turn to the checkpointed session."""

    turn = {
        "turn_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "query": state["user_query"],
        "resolved_query": state.get("resolved_query"),
        "context_used": bool(state.get("context_used")),
        "intent": state["intent"],
        "answer": state.get("answer") or "当前分支没有返回答案。",
        "generated_sql": state.get("generated_sql"),
        "citations": state.get("citations", []),
        "errors": state.get("errors", []),
        "metrics": state.get("metrics", {}),
    }
    return {"turns": [turn]}

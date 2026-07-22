from time import perf_counter

from app.graph.router import classify_intent
from app.graph.state import AgentState
from app.rag.service import handle_rag_question
from app.sql_agent.service import handle_sql_question


def route_node(state: AgentState) -> dict:
    return {"intent": classify_intent(state["user_query"])}


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
    result = await handle_sql_question(state["user_query"])
    result["metrics"] = {"sql_branch_ms": round((perf_counter() - started) * 1000, 2)}
    return result


async def rag_node(state: AgentState) -> dict:
    started = perf_counter()
    result = await handle_rag_question(state["user_query"])
    result["metrics"] = {"rag_branch_ms": round((perf_counter() - started) * 1000, 2)}
    return result


async def hybrid_node(state: AgentState) -> dict:
    started = perf_counter()
    sql_result = await handle_sql_question(state["user_query"])
    rag_result = await handle_rag_question(state["user_query"])
    return {
        "generated_sql": sql_result.get("generated_sql"),
        "sql_result": sql_result.get("sql_result"),
        "chart_spec": sql_result.get("chart_spec"),
        "retrieved_docs": rag_result.get("retrieved_docs", []),
        "citations": rag_result.get("citations", []),
        "answer": f"{sql_result['answer']}\n\n{rag_result['answer']}",
        "metrics": {"hybrid_branch_ms": round((perf_counter() - started) * 1000, 2)},
    }


def route_key(state: AgentState) -> str:
    return state["intent"]


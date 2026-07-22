from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    clarify_node,
    general_node,
    hybrid_node,
    rag_node,
    route_key,
    route_node,
    sql_node,
)
from app.graph.state import AgentState


@lru_cache
def get_graph() -> Any:
    builder = StateGraph(AgentState)
    builder.add_node("route", route_node)
    builder.add_node("sql", sql_node)
    builder.add_node("rag", rag_node)
    builder.add_node("hybrid", hybrid_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("general", general_node)

    builder.add_edge(START, "route")
    builder.add_conditional_edges(
        "route",
        route_key,
        {
            "sql": "sql",
            "rag": "rag",
            "hybrid": "hybrid",
            "clarify": "clarify",
            "general": "general",
        },
    )

    for node_name in ("sql", "rag", "hybrid", "clarify", "general"):
        builder.add_edge(node_name, END)

    return builder.compile()

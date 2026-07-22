from typing import Any, Literal, TypedDict

Intent = Literal["sql", "rag", "hybrid", "clarify", "general"]


class AgentState(TypedDict, total=False):
    user_query: str
    session_id: str
    intent: Intent
    clarification: str | None
    selected_tables: list[str]
    schema_context: str
    generated_sql: str | None
    sql_validation: dict[str, Any] | None
    sql_result: dict[str, Any] | None
    retrieved_docs: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    chart_spec: dict[str, Any] | None
    answer: str | None
    retry_count: int
    errors: list[str]
    metrics: dict[str, Any]

from typing import Annotated, Any, Literal, TypedDict

Intent = Literal["sql", "rag", "hybrid", "report", "clarify", "general"]
MAX_SESSION_TURNS = 20


def merge_turns(
    existing: list[dict[str, Any]],
    new: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [*existing, *new][-MAX_SESSION_TURNS:]


class AgentState(TypedDict, total=False):
    user_query: str
    resolved_query: str | None
    context_used: bool
    context_source_turn_id: str | None
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
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    tool_round_count: int
    report_artifact: dict[str, Any] | None
    chart_spec: dict[str, Any] | None
    answer: str | None
    retry_count: int
    errors: list[str]
    metrics: dict[str, Any]
    turns: Annotated[list[dict[str, Any]], merge_turns]

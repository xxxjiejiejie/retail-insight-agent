from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import RetailInsightError
from app.database.schema import load_schema_catalog
from app.llm.deepseek import TextGenerator, get_llm_client
from app.sql_agent.executor import execute_read_only_sql
from app.sql_agent.prompts import SQL_SYSTEM_PROMPT, build_sql_user_prompt


@dataclass(slots=True, frozen=True)
class SQLPlan:
    sql: str
    explanation: str
    chart: dict[str, str] | None


def validate_chart_spec(
    chart: dict[str, str] | None,
    result_columns: list[str],
) -> dict[str, str] | None:
    if chart is None:
        return None
    chart_type = chart.get("type")
    title = chart.get("title")
    x_field = chart.get("x_field")
    y_field = chart.get("y_field")
    if chart_type not in {"bar", "line", "pie", "scatter"}:
        return None
    if not all(isinstance(value, str) for value in (title, x_field, y_field)):
        return None
    assert isinstance(title, str)
    assert isinstance(x_field, str)
    assert isinstance(y_field, str)
    if len(title) > 80 or "<" in title or ">" in title:
        return None
    if x_field not in result_columns or y_field not in result_columns:
        return None
    return {
        "type": chart_type,
        "title": title,
        "x_field": x_field,
        "y_field": y_field,
    }


def parse_sql_plan(raw_content: str) -> SQLPlan:
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("SQL plan must be a JSON object")
    sql = payload.get("sql")
    explanation = payload.get("explanation")
    chart = payload.get("chart")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL plan is missing sql")
    if not isinstance(explanation, str):
        explanation = "已按用户问题生成经营分析查询。"
    if chart is not None and not isinstance(chart, dict):
        chart = None
    return SQLPlan(sql=sql.strip(), explanation=explanation.strip(), chart=chart)


async def handle_sql_question(
    query: str,
    *,
    llm_client: TextGenerator | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.llm_api_key and llm_client is None:
        return {
            "generated_sql": None,
            "sql_validation": None,
            "sql_result": None,
            "chart_spec": None,
            "answer": "已路由到经营数据分析分支，但请先在本地 .env 配置新的 LLM_API_KEY。",
            "errors": ["LLM_API_KEY_NOT_CONFIGURED"],
        }

    try:
        schema = await load_schema_catalog()
        client = llm_client or get_llm_client()
        llm_result = await client.generate_text(
            system=SQL_SYSTEM_PROMPT,
            user=build_sql_user_prompt(query, schema.context),
        )
        plan = parse_sql_plan(llm_result.content)
        query_result = await execute_read_only_sql(plan.sql, schema)
    except (RetailInsightError, json.JSONDecodeError, ValueError) as exc:
        return {
            "generated_sql": None,
            "sql_validation": None,
            "sql_result": None,
            "chart_spec": None,
            "answer": f"经营数据查询暂未完成：{exc}",
            "errors": [type(exc).__name__],
        }

    result_payload = asdict(query_result)
    return {
        "generated_sql": query_result.executed_sql,
        "sql_validation": {"is_safe": True},
        "sql_result": result_payload,
        "chart_spec": validate_chart_spec(plan.chart, query_result.columns),
        "answer": f"{plan.explanation} 查询完成，共返回 {query_result.row_count} 行结果。",
        "metrics": {
            "prompt_tokens": llm_result.prompt_tokens,
            "completion_tokens": llm_result.completion_tokens,
            "total_tokens": llm_result.total_tokens,
            "sql_execution_ms": query_result.execution_ms,
        },
    }

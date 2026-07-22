from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.core.errors import (
    DatabaseQueryError,
    IntegrationError,
    LLMResponseError,
    RetailInsightError,
    UnsafeSQLError,
)
from app.database.schema import load_schema_catalog
from app.llm.deepseek import TextGenerator, get_llm_client
from app.sql_agent.executor import execute_read_only_sql
from app.sql_agent.prompts import (
    SQL_SYSTEM_PROMPT,
    build_sql_repair_prompt,
    build_sql_user_prompt,
)


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


def _safe_retry_message(exc: Exception) -> str:
    if isinstance(exc, json.JSONDecodeError):
        return "输出不是有效 JSON"
    if isinstance(exc, ValueError):
        return str(exc)[:500]
    if isinstance(exc, (UnsafeSQLError, DatabaseQueryError, LLMResponseError)):
        return str(exc)[:500]
    return "查询计划未通过校验"


def _failure_result(
    *,
    answer: str,
    error_code: str,
    generated_sql: str | None,
    attempts: int,
    prompt_tokens: int,
    completion_tokens: int,
    llm_latency_ms: float,
    started: float,
) -> dict[str, Any]:
    return {
        "generated_sql": generated_sql,
        "sql_validation": {"is_safe": False, "errors": [answer]},
        "sql_result": None,
        "chart_spec": None,
        "answer": f"经营数据查询暂未完成：{answer}",
        "errors": [error_code],
        "metrics": {
            "attempt_count": attempts,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "llm_latency_ms": round(llm_latency_ms, 2),
            "total_latency_ms": round((perf_counter() - started) * 1000, 2),
        },
    }


async def handle_sql_question(
    query: str,
    *,
    llm_client: TextGenerator | None = None,
    engine: AsyncEngine | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    if not settings.llm_api_key and llm_client is None:
        return _failure_result(
            answer="请先在本地 .env 配置新的 LLM_API_KEY",
            error_code="LLM_API_KEY_NOT_CONFIGURED",
            generated_sql=None,
            attempts=0,
            prompt_tokens=0,
            completion_tokens=0,
            llm_latency_ms=0,
            started=started,
        )

    try:
        schema = await load_schema_catalog(engine)
        client = llm_client or get_llm_client()
    except RetailInsightError as exc:
        return _failure_result(
            answer=str(exc),
            error_code=type(exc).__name__,
            generated_sql=None,
            attempts=0,
            prompt_tokens=0,
            completion_tokens=0,
            llm_latency_ms=0,
            started=started,
        )

    prompt = build_sql_user_prompt(query, schema.context, settings.data_as_of_date)
    attempts = 0
    prompt_tokens = 0
    completion_tokens = 0
    llm_latency_ms = 0.0
    last_sql: str | None = None
    last_error = "查询计划未完成"
    last_error_code = "SQL_PLAN_FAILED"

    while attempts <= settings.max_sql_retries:
        attempts += 1
        previous_output = ""
        try:
            llm_result = await client.generate_text(
                system=SQL_SYSTEM_PROMPT,
                user=prompt,
            )
            prompt_tokens += llm_result.prompt_tokens
            completion_tokens += llm_result.completion_tokens
            llm_latency_ms += llm_result.latency_ms
            previous_output = llm_result.content
            plan = parse_sql_plan(llm_result.content)
            last_sql = plan.sql
            query_result = await execute_read_only_sql(plan.sql, schema, engine=engine)
        except IntegrationError as exc:
            return _failure_result(
                answer=str(exc),
                error_code=type(exc).__name__,
                generated_sql=last_sql,
                attempts=attempts,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                llm_latency_ms=llm_latency_ms,
                started=started,
            )
        except (
            UnsafeSQLError,
            DatabaseQueryError,
            LLMResponseError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            last_error = _safe_retry_message(exc)
            last_error_code = type(exc).__name__
            if attempts > settings.max_sql_retries:
                break
            prompt = build_sql_repair_prompt(
                query,
                schema.context,
                settings.data_as_of_date,
                previous_output or last_sql or "未生成可解析的查询计划",
                last_error,
            )
            continue

        result_payload = asdict(query_result)
        return {
            "generated_sql": query_result.executed_sql,
            "sql_validation": {"is_safe": True, "errors": []},
            "sql_result": result_payload,
            "chart_spec": validate_chart_spec(plan.chart, query_result.columns),
            "answer": f"{plan.explanation} 查询完成，共返回 {query_result.row_count} 行结果。",
            "errors": [],
            "metrics": {
                "attempt_count": attempts,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "llm_latency_ms": round(llm_latency_ms, 2),
                "sql_execution_ms": query_result.execution_ms,
                "total_latency_ms": round((perf_counter() - started) * 1000, 2),
            },
        }

    return _failure_result(
        answer=last_error,
        error_code=last_error_code,
        generated_sql=last_sql,
        attempts=attempts,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        llm_latency_ms=llm_latency_ms,
        started=started,
    )

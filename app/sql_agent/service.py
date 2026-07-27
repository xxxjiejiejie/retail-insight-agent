from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlglot import exp, parse_one

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
from app.observability.langsmith import observe_chain
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


TOP_N_PATTERN = re.compile(r"(?:最高|最低)的?\s*(\d+)|前\s*(\d+)")
SINGLE_EXTREME_HINTS = ("星期几", "哪个", "哪家", "哪一", "什么", "一笔", "一项", "只返回")
SQL_PLAN_MAX_TOKENS = 2_400


def required_result_limit(query: str) -> int | None:
    match = TOP_N_PATTERN.search(query)
    if match:
        return int(match.group(1) or match.group(2))
    if ("最高" in query or "最低" in query) and any(
        hint in query for hint in SINGLE_EXTREME_HINTS
    ):
        return 1
    return None


def validate_question_constraints(query: str, sql: str) -> None:
    normalized_query = query.replace(" ", "")
    normalized_sql = sql.casefold()
    if "退货件次" in normalized_query and "售出明细数" in normalized_query:
        if "left join orders" in normalized_sql:
            raise ValueError("已完成订单明细统计不能使用 LEFT JOIN orders 绕过状态和日期过滤")
        if "sum(oi.quantity)" in normalized_sql:
            raise ValueError("售出明细数必须 COUNT(order_item_id)，不能 SUM(quantity)")
    if "平均折扣率" in normalized_query:
        if "avg(" in normalized_sql and "* 100" not in normalized_sql:
            raise ValueError("平均折扣率必须使用 AVG(discount) * 100 转为百分数")
    if "完成订单和取消订单分别" in normalized_query:
        group_by_match = re.search(
            r"group\s+by(.+?)(?:order\s+by|limit|$)", normalized_sql, re.DOTALL
        )
        if group_by_match and "status" in group_by_match.group(1):
            raise ValueError("完成/取消订单分别统计必须按区域聚合，不能按订单状态分组展开")
        if "case when" not in normalized_sql:
            raise ValueError("完成/取消订单分别统计必须使用条件聚合返回两列")
        if "canceled" in normalized_sql:
            raise ValueError("订单取消状态必须使用 Schema 中的 cancelled 拼写")
    required_limit = required_result_limit(query)
    if required_limit is None:
        return
    statement = parse_one(sql, read="mysql")
    if not statement.args.get("order"):
        raise ValueError(f"问题要求排序后只返回 {required_limit} 项，但 SQL 缺少 ORDER BY")
    limit = statement.args.get("limit")
    limit_expression = limit.expression if isinstance(limit, exp.Limit) else None
    if not isinstance(limit_expression, exp.Literal) or not limit_expression.is_int:
        raise ValueError(f"问题要求只返回 {required_limit} 项，但 SQL 缺少明确 LIMIT")
    if int(limit_expression.this) != required_limit:
        raise ValueError(
            f"问题要求只返回 {required_limit} 项，但 SQL 使用了 LIMIT {limit_expression.this}"
        )


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
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        payload = None
        for index, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                payload = candidate
                break
        if payload is None:
            raise original_error
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
                max_tokens=SQL_PLAN_MAX_TOKENS,
            )
            prompt_tokens += llm_result.prompt_tokens
            completion_tokens += llm_result.completion_tokens
            llm_latency_ms += llm_result.latency_ms
            previous_output = llm_result.content
            plan = parse_sql_plan(llm_result.content)
            last_sql = plan.sql
            validate_question_constraints(query, plan.sql)
            async with observe_chain(
                "sql.execute",
                inputs={"sql": plan.sql, "attempt": attempts},
                tags=["sql", "database"],
                metadata={"read_only": True},
            ) as sql_span:
                query_result = await execute_read_only_sql(plan.sql, schema, engine=engine)
                await sql_span.end(
                    {
                        "columns": query_result.columns,
                        "row_count": query_result.row_count,
                        "execution_ms": query_result.execution_ms,
                        "executed_sql": query_result.executed_sql,
                    }
                )
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

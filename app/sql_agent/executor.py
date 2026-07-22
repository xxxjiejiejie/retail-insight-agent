from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlglot import exp, parse_one

from app.core.config import get_settings
from app.core.errors import DatabaseQueryError, UnsafeSQLError
from app.database.engine import get_business_engine
from app.database.schema import SchemaCatalog
from app.sql_agent.validator import validate_read_only_sql


@dataclass(slots=True, frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: float
    executed_sql: str


def enforce_limit(sql: str, max_rows: int, *, dialect: str = "mysql") -> str:
    statement = parse_one(sql, read=dialect)
    limit = statement.args.get("limit")
    current_value: int | None = None
    if isinstance(limit, exp.Limit) and isinstance(limit.expression, exp.Literal):
        try:
            current_value = int(limit.expression.this)
        except (TypeError, ValueError):
            current_value = None
    if current_value is None or current_value > max_rows:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return statement.sql(dialect=dialect)


async def execute_read_only_sql(
    sql: str,
    schema: SchemaCatalog,
    *,
    engine: AsyncEngine | None = None,
) -> QueryResult:
    settings = get_settings()
    validation = validate_read_only_sql(
        sql,
        allowed_tables=schema.tables,
        allowed_columns=schema.columns,
    )
    if not validation.is_safe or not validation.normalized_sql:
        raise UnsafeSQLError("；".join(validation.errors))

    limited_sql = enforce_limit(validation.normalized_sql, settings.max_result_rows)
    business_engine = engine or get_business_engine()
    started = perf_counter()
    try:
        async with asyncio.timeout(settings.sql_query_timeout_seconds):
            async with business_engine.connect() as connection:
                cursor = await connection.execute(text(limited_sql))
                rows = [dict(row) for row in cursor.mappings().fetchall()]
                columns = list(cursor.keys())
    except TimeoutError as exc:
        raise DatabaseQueryError("SQL 查询超过时间限制") from exc
    except SQLAlchemyError as exc:
        raise DatabaseQueryError("SQL 查询执行失败") from exc

    return QueryResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_ms=round((perf_counter() - started) * 1000, 2),
        executed_sql=limited_sql,
    )

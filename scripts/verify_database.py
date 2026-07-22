"""Verify the local MySQL seed data through the application's read-only path."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.sql_agent.executor import execute_read_only_sql


async def main() -> None:
    engine = get_business_engine()
    try:
        async with engine.connect() as connection:
            grant_rows = await connection.execute(text("SHOW GRANTS"))
            grants = [str(row[0]) for row in grant_rows]
        if not any("SELECT" in grant and "retail_insight" in grant for grant in grants):
            raise RuntimeError("只读账号缺少 retail_insight 的 SELECT 权限")
        if any("ALL PRIVILEGES" in grant for grant in grants):
            raise RuntimeError("业务查询账号权限过高")

        schema = await load_schema_catalog(engine)
        result = await execute_read_only_sql(
            """
            SELECT s.region,
                   COUNT(DISTINCT o.order_id) AS order_count,
                   ROUND(SUM(oi.quantity * oi.sale_price * (1 - oi.discount)), 2) AS revenue
            FROM stores AS s
            JOIN orders AS o ON o.store_id = s.store_id
            JOIN order_items AS oi ON oi.order_id = o.order_id
            WHERE o.status = 'completed'
              AND o.order_date >= '2026-04-01'
              AND o.order_date < '2026-07-01'
            GROUP BY s.region
            ORDER BY revenue DESC
            """,
            schema,
            engine=engine,
        )
        print(f"tables={len(schema.tables)} names={','.join(sorted(schema.tables))}")
        print("readonly_grant=verified")
        print(f"rows={result.row_count} execution_ms={result.execution_ms}")
        for row in result.rows:
            print(row)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

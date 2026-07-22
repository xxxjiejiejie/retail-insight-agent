import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.database.schema import load_schema_catalog
from app.llm.deepseek import LLMTextResponse
from app.sql_agent.executor import execute_read_only_sql
from app.sql_agent.service import handle_sql_question

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Set RUN_DB_TESTS=1 when the local MySQL container is running",
)


@pytest.mark.asyncio
async def test_read_only_database_query() -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        schema = await load_schema_catalog(engine)
        result = await execute_read_only_sql(
            "SELECT region, COUNT(*) AS store_count FROM stores GROUP BY region",
            schema,
            engine=engine,
        )
        assert result.row_count == 4
        assert {row["region"] for row in result.rows} == {"华东", "华南", "华北", "西南"}
    finally:
        await engine.dispose()


class FakeSQLGenerator:
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        assert "Text-to-SQL" in system
        assert "Schema" in user
        return LLMTextResponse(
            content=(
                '{"sql":"SELECT region, COUNT(*) AS store_count FROM stores '
                'GROUP BY region ORDER BY store_count DESC",'
                '"explanation":"统计各区域门店数量",'
                '"chart":{"type":"bar","title":"各区域门店数量",'
                '"x_field":"region","y_field":"store_count"}}'
            ),
            prompt_tokens=120,
            completion_tokens=50,
        )


class DerivedTableSQLGenerator:
    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        return LLMTextResponse(
            content=(
                '{"sql":"SELECT s.store_name, '
                'ROUND(COALESCE(rev.actual_revenue, 0) / st.revenue_target * 100, 2) '
                'AS completion_rate FROM stores s '
                'JOIN sales_targets st ON s.store_id = st.store_id '
                "AND st.target_month = '2026-06-01' "
                'LEFT JOIN (SELECT o.store_id, '
                'SUM(oi.quantity * oi.sale_price * (1 - oi.discount)) AS actual_revenue '
                'FROM orders o JOIN order_items oi ON o.order_id = oi.order_id '
                "WHERE o.status = 'completed' AND o.order_date >= '2026-06-01' "
                "AND o.order_date < '2026-07-01' GROUP BY o.store_id) rev "
                'ON s.store_id = rev.store_id '
                'WHERE COALESCE(rev.actual_revenue, 0) < st.revenue_target '
                'ORDER BY completion_rate ASC",'
                '"explanation":"查询未完成目标的门店",'
                '"chart":{"type":"bar","title":"未达标门店完成率",'
                '"x_field":"store_name","y_field":"completion_rate"}}'
            ),
            prompt_tokens=200,
            completion_tokens=100,
        )


@pytest.mark.asyncio
async def test_mock_llm_to_real_database_chain() -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        result = await handle_sql_question(
            "各区域有多少家门店？",
            llm_client=FakeSQLGenerator(),
            engine=engine,
        )
        assert result["sql_result"]["row_count"] == 4
        assert result["chart_spec"]["x_field"] == "region"
        assert result["metrics"]["total_tokens"] == 170
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_derived_table_mock_llm_to_real_database_chain() -> None:
    engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        result = await handle_sql_question(
            "2026年6月哪些门店没有完成销售目标？",
            llm_client=DerivedTableSQLGenerator(),
            engine=engine,
        )
        assert result["errors"] == []
        assert result["sql_result"]["row_count"] > 0
        assert result["metrics"]["attempt_count"] == 1
    finally:
        await engine.dispose()

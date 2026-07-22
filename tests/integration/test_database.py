import os

import pytest

from app.database.engine import get_business_engine
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
    engine = get_business_engine()
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


@pytest.mark.asyncio
async def test_mock_llm_to_real_database_chain() -> None:
    result = await handle_sql_question(
        "各区域有多少家门店？",
        llm_client=FakeSQLGenerator(),
    )
    assert result["sql_result"]["row_count"] == 4
    assert result["chart_spec"]["x_field"] == "region"
    assert result["metrics"]["total_tokens"] == 170

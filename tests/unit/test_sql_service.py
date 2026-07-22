from typing import Any

import pytest

from app.core.errors import IntegrationError
from app.database.schema import SchemaCatalog
from app.llm.deepseek import LLMTextResponse
from app.sql_agent.executor import QueryResult
from app.sql_agent.service import handle_sql_question, parse_sql_plan, validate_chart_spec


def test_parses_sql_plan_json() -> None:
    plan = parse_sql_plan(
        '{"sql":"SELECT region, COUNT(*) AS total FROM stores GROUP BY region",'
        '"explanation":"统计区域门店数",'
        '"chart":{"type":"bar","title":"门店数","x_field":"region",'
        '"y_field":"total"}}'
    )
    assert plan.sql.startswith("SELECT")
    assert plan.chart is not None


def test_rejects_chart_fields_not_in_query_result() -> None:
    chart = {
        "type": "bar",
        "title": "测试",
        "x_field": "unknown",
        "y_field": "total",
    }
    assert validate_chart_spec(chart, ["region", "total"]) is None


class SequenceGenerator:
    def __init__(self, responses: list[LLMTextResponse]):
        self.responses = responses
        self.prompts: list[str] = []

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        self.prompts.append(user)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_retries_invalid_json_and_accumulates_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_schema(engine: object | None = None) -> SchemaCatalog:
        return SchemaCatalog(columns={"stores": {"region"}}, context="TABLE stores (region TEXT)")

    async def fake_execute(
        sql: str,
        schema: SchemaCatalog,
        **_: Any,
    ) -> QueryResult:
        assert sql.startswith("SELECT")
        return QueryResult(
            columns=["region"],
            rows=[{"region": "华东"}],
            row_count=1,
            execution_ms=3.5,
            executed_sql="SELECT region FROM stores LIMIT 500",
        )

    monkeypatch.setattr("app.sql_agent.service.load_schema_catalog", fake_schema)
    monkeypatch.setattr("app.sql_agent.service.execute_read_only_sql", fake_execute)
    generator = SequenceGenerator(
        [
            LLMTextResponse("not-json", 10, 2, latency_ms=12.0),
            LLMTextResponse(
                '{"sql":"SELECT region FROM stores","explanation":"查询区域","chart":null}',
                20,
                5,
                latency_ms=18.0,
            ),
        ]
    )

    result = await handle_sql_question("有哪些区域？", llm_client=generator)

    assert result["metrics"]["attempt_count"] == 2
    assert result["metrics"]["total_tokens"] == 37
    assert result["metrics"]["llm_latency_ms"] == 30.0
    assert "输出不是有效 JSON" in generator.prompts[1]
    assert "2026-06-30" in generator.prompts[1]


@pytest.mark.asyncio
async def test_external_api_error_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingGenerator:
        calls = 0

        async def generate_text(
            self,
            *,
            system: str,
            user: str,
            max_tokens: int = 1_200,
        ) -> LLMTextResponse:
            self.calls += 1
            raise IntegrationError("DeepSeek API 返回 HTTP 429")

    async def fake_schema(engine: object | None = None) -> SchemaCatalog:
        return SchemaCatalog(columns={"stores": {"region"}}, context="TABLE stores (region TEXT)")

    monkeypatch.setattr("app.sql_agent.service.load_schema_catalog", fake_schema)
    generator = FailingGenerator()

    result = await handle_sql_question("有哪些区域？", llm_client=generator)

    assert generator.calls == 1
    assert result["metrics"]["attempt_count"] == 1
    assert result["errors"] == ["IntegrationError"]
    assert "HTTP 429" in result["answer"]
    assert "Traceback" not in result["answer"]

from typing import Any

import pytest

from app.core.errors import IntegrationError
from app.database.schema import SchemaCatalog
from app.llm.deepseek import LLMTextResponse
from app.sql_agent.executor import QueryResult
from app.sql_agent.service import (
    handle_sql_question,
    parse_sql_plan,
    required_result_limit,
    validate_chart_spec,
    validate_question_constraints,
)


def test_parses_sql_plan_json() -> None:
    plan = parse_sql_plan(
        '{"sql":"SELECT region, COUNT(*) AS total FROM stores GROUP BY region",'
        '"explanation":"统计区域门店数",'
        '"chart":{"type":"bar","title":"门店数","x_field":"region",'
        '"y_field":"total"}}'
    )
    assert plan.sql.startswith("SELECT")
    assert plan.chart is not None


def test_extracts_json_plan_surrounded_by_explanation() -> None:
    plan = parse_sql_plan(
        '查询计划如下：\n{"sql":"SELECT region FROM stores",'
        '"explanation":"查询区域","chart":null}\n以上为只读查询。'
    )

    assert plan.sql == "SELECT region FROM stores"


def test_detects_required_top_n_limit() -> None:
    assert required_result_limit("销售额最高的5家门店") == 5
    assert required_result_limit("星期几的销售额最高？") == 1
    assert required_result_limit("各区域销售额是多少？") is None


def test_rejects_extreme_query_without_exact_limit() -> None:
    with pytest.raises(ValueError, match="LIMIT"):
        validate_question_constraints(
            "星期几的销售额最高？",
            "SELECT DAYNAME(order_date), SUM(amount) FROM orders "
            "GROUP BY DAYNAME(order_date) ORDER BY SUM(amount) DESC",
        )

    validate_question_constraints(
        "星期几的销售额最高？",
        "SELECT DAYNAME(order_date), SUM(amount) FROM orders "
        "GROUP BY DAYNAME(order_date) ORDER BY SUM(amount) DESC LIMIT 1",
    )


def test_rejects_ambiguous_status_aggregation_shape() -> None:
    with pytest.raises(ValueError, match="按区域聚合"):
        validate_question_constraints(
            "各区域完成订单和取消订单分别有多少",
            "SELECT region, status, COUNT(*) FROM orders "
            "GROUP BY region, status ORDER BY region",
        )

    with pytest.raises(ValueError, match="LEFT JOIN"):
        validate_question_constraints(
            "各商品类别的退货件次和售出明细数是多少",
            "SELECT p.category, COUNT(oi.order_item_id) FROM products p "
            "LEFT JOIN order_items oi ON oi.product_id = p.product_id "
            "LEFT JOIN orders o ON o.order_id = oi.order_id",
        )


def test_rejects_percent_and_status_spelling_mistakes() -> None:
    with pytest.raises(ValueError, match="百分数"):
        validate_question_constraints(
            "各商品类别的平均折扣率是多少",
            "SELECT category, ROUND(AVG(discount), 2) FROM products GROUP BY category",
        )

    with pytest.raises(ValueError, match="cancelled"):
        validate_question_constraints(
            "各区域完成订单和取消订单分别有多少",
            "SELECT region, SUM(CASE WHEN status = 'canceled' THEN 1 ELSE 0 END) "
            "FROM orders GROUP BY region",
        )


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

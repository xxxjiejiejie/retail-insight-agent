from app.sql_agent.service import parse_sql_plan, validate_chart_spec


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

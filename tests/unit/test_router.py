import json
from pathlib import Path

import pytest

from app.graph.router import classify_intent


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("华东区域本月销售额是多少", "sql"),
        ("退换货处理制度是什么", "rag"),
        ("退货率是否符合退换货管理规定", "hybrid"),
        ("这个呢", "clarify"),
        ("你好，请介绍一下你的能力", "general"),
    ],
)
def test_classify_intent(query: str, expected: str) -> None:
    assert classify_intent(query) == expected


def test_sql_evaluation_questions_route_to_sql() -> None:
    cases = json.loads(
        Path("data/eval/sql_smoke_cases.json").read_text(encoding="utf-8")
    )
    for case in cases:
        assert classify_intent(case["question"]) == "sql", case["id"]


def test_answerable_rag_evaluation_questions_route_to_rag() -> None:
    cases = json.loads(Path("data/eval/rag_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        if case["expect_answer"]:
            assert classify_intent(case["question"]) == "rag", case["id"]


def test_combined_metric_and_policy_question_routes_to_hybrid() -> None:
    query = "2026年6月各门店销售目标完成率，并说明未达标门店按照什么制度处理"
    assert classify_intent(query) == "hybrid"

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

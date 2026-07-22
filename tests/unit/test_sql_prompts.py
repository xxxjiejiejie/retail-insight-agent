from datetime import date

from app.sql_agent.prompts import build_sql_user_prompt, build_time_context


def test_relative_time_uses_dataset_as_of_date() -> None:
    context = build_time_context(date(2026, 6, 30))
    assert "2026-06-30" in context
    assert "[2026-06-01, 2026-07-01)" in context
    assert "[2026-04-01, 2026-07-01)" in context


def test_prompt_forbids_database_current_time() -> None:
    prompt = build_sql_user_prompt(
        "本月销售额是多少？",
        "TABLE orders (order_date DATETIME)",
        date(2026, 6, 30),
    )
    assert "不得使用数据库当前时间" in prompt
    assert "本月销售额是多少" in prompt

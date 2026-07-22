from app.sql_agent.validator import validate_read_only_sql


def test_allows_select_from_whitelisted_table() -> None:
    result = validate_read_only_sql(
        "SELECT region, SUM(amount) FROM orders GROUP BY region LIMIT 20",
        allowed_tables={"orders"},
    )
    assert result.is_safe
    assert result.referenced_tables == ["orders"]


def test_rejects_update() -> None:
    result = validate_read_only_sql("UPDATE orders SET amount = 0")
    assert not result.is_safe


def test_rejects_unapproved_table() -> None:
    result = validate_read_only_sql(
        "SELECT * FROM users",
        allowed_tables={"orders"},
    )
    assert not result.is_safe
    assert any("未授权" in error for error in result.errors)


def test_rejects_multiple_statements() -> None:
    result = validate_read_only_sql("SELECT 1; DROP TABLE orders")
    assert not result.is_safe


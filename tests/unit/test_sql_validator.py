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


def test_rejects_unknown_column() -> None:
    result = validate_read_only_sql(
        "SELECT secret_value FROM orders",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"order_id", "status"}},
    )
    assert not result.is_safe
    assert any("未授权的字段" in error for error in result.errors)


def test_allows_cte_derived_column() -> None:
    result = validate_read_only_sql(
        "WITH totals AS (SELECT store_id, COUNT(*) AS order_count FROM orders "
        "GROUP BY store_id) SELECT store_id, order_count FROM totals",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"store_id"}},
    )
    assert result.is_safe


def test_allows_subquery_derived_columns() -> None:
    result = validate_read_only_sql(
        "SELECT rev.store_id, rev.actual_revenue FROM "
        "(SELECT o.store_id, SUM(o.amount) AS actual_revenue FROM orders o "
        "GROUP BY o.store_id) rev",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"store_id", "amount"}},
    )
    assert result.is_safe


def test_rejects_unknown_subquery_output_column() -> None:
    result = validate_read_only_sql(
        "SELECT rev.secret_value FROM "
        "(SELECT o.store_id FROM orders o) rev",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"store_id"}},
    )
    assert not result.is_safe
    assert any("rev.secret_value" in error for error in result.errors)


def test_rejects_unknown_physical_column_inside_subquery() -> None:
    result = validate_read_only_sql(
        "SELECT rev.actual_revenue FROM "
        "(SELECT SUM(o.secret_value) AS actual_revenue FROM orders o) rev",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"store_id", "amount"}},
    )
    assert not result.is_safe
    assert any("o.secret_value" in error for error in result.errors)


def test_rejects_sleep_function() -> None:
    result = validate_read_only_sql("SELECT SLEEP(10)")
    assert not result.is_safe
    assert any("禁止的函数" in error for error in result.errors)


def test_allows_order_by_select_alias() -> None:
    result = validate_read_only_sql(
        "SELECT store_id, COUNT(*) AS order_count FROM orders "
        "GROUP BY store_id ORDER BY order_count DESC",
        allowed_tables={"orders"},
        allowed_columns={"orders": {"store_id"}},
    )
    assert result.is_safe

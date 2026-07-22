from app.sql_agent.executor import enforce_limit


def test_adds_limit_when_missing() -> None:
    normalized = enforce_limit("SELECT order_id FROM orders", 100)
    assert "LIMIT 100" in normalized


def test_tightens_excessive_limit() -> None:
    normalized = enforce_limit("SELECT order_id FROM orders LIMIT 999", 100)
    assert "LIMIT 100" in normalized


def test_keeps_smaller_limit() -> None:
    normalized = enforce_limit("SELECT order_id FROM orders LIMIT 10", 100)
    assert "LIMIT 10" in normalized

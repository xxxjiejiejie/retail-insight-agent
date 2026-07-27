from app.core.config import Settings
from app.observability import langsmith as langsmith_module


def test_langsmith_requires_switch_and_key() -> None:
    disabled = Settings(
        _env_file=None,
        langsmith_tracing=False,
        langsmith_api_key="test-key",
    )
    missing_key = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key="",
    )
    enabled = Settings(
        _env_file=None,
        langsmith_tracing=True,
        langsmith_api_key="test-key",
    )

    assert disabled.langsmith_enabled is False
    assert missing_key.langsmith_enabled is False
    assert enabled.langsmith_enabled is True


def test_sanitizer_removes_secrets_rows_and_long_policy_content(
    monkeypatch,
) -> None:
    settings = Settings(
        _env_file=None,
        langsmith_max_string_length=200,
        langsmith_policy_excerpt_length=100,
    )
    monkeypatch.setattr(langsmith_module, "get_settings", lambda: settings)
    payload = {
        "headers": {"authorization": "Bearer private"},
        "database_url": "mysql://user:password@localhost/db",
        "note": "sk-abcdefghijklmnopqrstuvwxyz123456",
        "sql_result": {
            "columns": ["store_name", "sales"],
            "rows": [{"store_name": "上海店", "sales": 100}],
            "row_count": 1,
        },
        "retrieved_docs": [{"content": "制" * 180}],
        "metrics": {"prompt_tokens": 12, "completion_tokens": 3},
    }

    sanitized = langsmith_module.sanitize_trace_payload(payload)

    assert sanitized["headers"] == "[REDACTED]"
    assert sanitized["database_url"] == "[REDACTED]"
    assert "sk-" not in sanitized["note"]
    assert sanitized["sql_result"]["rows"] == {"omitted": True, "row_count": 1}
    assert sanitized["sql_result"]["row_count"] == 1
    assert sanitized["metrics"]["prompt_tokens"] == 12
    content = sanitized["retrieved_docs"][0]["content"]
    assert content.startswith("制" * 100)
    assert "TRUNCATED" in content


def test_disabled_request_trace_keeps_graph_config(
    monkeypatch,
) -> None:
    settings = Settings(
        _env_file=None,
        langsmith_tracing=False,
        langsmith_api_key="test-key",
    )
    monkeypatch.setattr(langsmith_module, "get_settings", lambda: settings)
    config = {"configurable": {"thread_id": "session-1"}}

    with langsmith_module.trace_agent_request(
        session_id="session-1",
        query="查询销售额",
        config=config,
    ) as (traced_config, tracer):
        assert traced_config == config
        assert tracer is None

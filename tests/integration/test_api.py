import httpx
import pytest

from app.api.routes import chat as chat_module
from app.api.routes import metadata as metadata_module
from app.core.errors import DatabaseQueryError
from app.database.schema import SchemaCatalog, SchemaColumn
from app.graph import nodes
from app.graph.persistence import open_checkpointer
from app.graph.workflow import build_graph
from app.main import app


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


@pytest.mark.asyncio
async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_schema_metadata_returns_read_only_catalog(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_catalog() -> SchemaCatalog:
        return SchemaCatalog(
            columns={"orders": {"order_id", "status"}},
            context="TABLE orders (order_id INTEGER, status VARCHAR)",
            details={
                "orders": [
                    SchemaColumn("order_id", "INTEGER", False),
                    SchemaColumn("status", "VARCHAR(32)", False),
                ]
            },
        )

    monkeypatch.setattr(metadata_module, "load_schema_catalog", fake_catalog)
    response = await client.get("/api/v1/metadata/schema")

    assert response.status_code == 200
    assert response.json() == {
        "tables": [
            {
                "name": "orders",
                "columns": [
                    {"name": "order_id", "type": "INTEGER", "nullable": False},
                    {"name": "status", "type": "VARCHAR(32)", "nullable": False},
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_schema_metadata_hides_database_error(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_catalog() -> SchemaCatalog:
        raise DatabaseQueryError("mysql://user:secret@database/internal")

    monkeypatch.setattr(metadata_module, "load_schema_catalog", failing_catalog)
    response = await client.get("/api/v1/metadata/schema")

    assert response.status_code == 503
    assert response.json()["detail"] == "经营数据库元数据暂时不可用。"
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_policy_metadata_lists_eight_documents(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/metadata/policies")

    assert response.status_code == 200
    documents = response.json()["documents"]
    assert len(documents) == 8
    assert all(document["section_count"] > 0 for document in documents)
    assert all(document["chunk_count"] > 0 for document in documents)


@pytest.mark.asyncio
async def test_chat_routes_sql_question(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeGraph:
        async def ainvoke(self, initial_state: dict, config: dict) -> dict:
            return {
                **initial_state,
                "intent": "sql",
                "answer": "查询完成。",
                "errors": [],
                "metrics": {"total_tokens": 10},
            }

    monkeypatch.setattr(chat_module, "get_graph", lambda: FakeGraph())
    response = await client.post(
        "/api/v1/chat",
        json={"query": "本月各区域销售额排名", "session_id": "test-session"},
    )
    assert response.status_code == 200
    assert response.json()["intent"] == "sql"
    assert response.json()["errors"] == []


@pytest.mark.asyncio
async def test_chat_stream_emits_progress_and_result(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStreamGraph:
        async def astream(self, initial_state: dict, config: dict, stream_mode: str):
            assert config["configurable"]["thread_id"] == "stream-session"
            assert stream_mode == "updates"
            yield {"route": {"intent": "general"}}
            yield {"general": {"answer": "流式回答", "errors": [], "metrics": {}}}
            yield {"persist_turn": {"turns": []}}

    monkeypatch.setattr(chat_module, "get_graph", lambda: FakeStreamGraph())
    response = await client.post(
        "/api/v1/chat/stream",
        json={"query": "你好", "session_id": "stream-session"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: node" in response.text
    assert '"node":"general"' in response.text
    assert "event: result" in response.text
    assert "流式回答" in response.text
    assert "event: done" in response.text


@pytest.mark.asyncio
async def test_chat_stream_hides_internal_graph_errors(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingGraph:
        async def astream(self, initial_state: dict, config: dict, stream_mode: str):
            raise RuntimeError("internal connection string and stack")
            yield

    monkeypatch.setattr(chat_module, "get_graph", lambda: FailingGraph())
    response = await client.post(
        "/api/v1/chat/stream",
        json={"query": "查询销售额", "session_id": "failing-session"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "请求处理失败，请稍后重试" in response.text
    assert "connection string" not in response.text
    assert "event: done" in response.text


@pytest.mark.asyncio
async def test_session_history_persists_and_can_be_deleted(
    client: httpx.AsyncClient,
    tmp_path,
) -> None:
    async with open_checkpointer(str(tmp_path / "sessions.db")) as checkpointer:
        graph = build_graph(checkpointer)
        app.state.graph = graph
        app.state.checkpointer = checkpointer
        try:
            for query in ("你好", "你能做什么"):
                response = await client.post(
                    "/api/v1/chat",
                    json={"query": query, "session_id": "persistent-session"},
                )
                assert response.status_code == 200

            history = await client.get("/api/v1/sessions/persistent-session")
            assert history.status_code == 200
            turns = history.json()["turns"]
            assert [turn["query"] for turn in turns] == ["你好", "你能做什么"]

            deleted = await client.delete("/api/v1/sessions/persistent-session")
            assert deleted.status_code == 200
            assert deleted.json()["deleted"] is True

            empty_history = await client.get("/api/v1/sessions/persistent-session")
            assert empty_history.json()["turns"] == []
        finally:
            del app.state.graph
            del app.state.checkpointer


@pytest.mark.asyncio
async def test_contextual_followup_uses_checkpointed_analytical_turn(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    received_queries: list[str] = []

    async def fake_sql_handler(query: str) -> dict:
        received_queries.append(query)
        return {
            "answer": "模拟数据回答",
            "generated_sql": "SELECT 1",
            "errors": [],
            "metrics": {"attempt_count": 1},
        }

    monkeypatch.setattr(nodes, "handle_sql_question", fake_sql_handler)
    async with open_checkpointer(str(tmp_path / "context-sessions.db")) as checkpointer:
        graph = build_graph(checkpointer)
        app.state.graph = graph
        app.state.checkpointer = checkpointer
        try:
            first = await client.post(
                "/api/v1/chat",
                json={
                    "query": "2026年第二季度各区域销售额是多少？",
                    "session_id": "context-session",
                },
            )
            second = await client.post(
                "/api/v1/chat",
                json={"query": "那华东呢", "session_id": "context-session"},
            )

            assert first.status_code == 200
            assert second.status_code == 200
            second_body = second.json()
            assert second_body["intent"] == "sql"
            assert second_body["context_used"] is True
            assert "第二季度各区域销售额" in second_body["resolved_query"]
            assert "那华东呢" in received_queries[-1]

            history = await client.get("/api/v1/sessions/context-session")
            turns = history.json()["turns"]
            assert len(turns) == 2
            assert turns[-1]["query"] == "那华东呢"
            assert turns[-1]["context_used"] is True
        finally:
            del app.state.graph
            del app.state.checkpointer


@pytest.mark.asyncio
async def test_session_history_replays_distinct_result_snapshots(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def fake_sql_handler(query: str) -> dict:
        value = 10 if "销售额" in query else 20
        return {
            "answer": f"结果为 {value}",
            "generated_sql": f"SELECT {value} AS metric_value",
            "sql_result": {
                "columns": ["metric_value"],
                "rows": [{"metric_value": value}],
                "row_count": 1,
                "execution_ms": 1.0,
                "executed_sql": f"SELECT {value} AS metric_value",
            },
            "chart_spec": {
                "type": "bar",
                "title": "指标",
                "x_field": "metric_name",
                "y_field": "metric_value",
            },
            "errors": [],
            "metrics": {"attempt_count": 1},
        }

    monkeypatch.setattr(nodes, "handle_sql_question", fake_sql_handler)
    async with open_checkpointer(str(tmp_path / "result-history.db")) as checkpointer:
        graph = build_graph(checkpointer)
        app.state.graph = graph
        app.state.checkpointer = checkpointer
        try:
            for query in (
                "2026年第二季度各区域销售额是多少？",
                "2026年6月各门店订单数是多少？",
            ):
                response = await client.post(
                    "/api/v1/chat",
                    json={"query": query, "session_id": "result-history-session"},
                )
                assert response.status_code == 200

            history = await client.get("/api/v1/sessions/result-history-session")
            turns = history.json()["turns"]
            assert len(turns) == 2
            assert turns[0]["answer"] == "结果为 10"
            assert turns[0]["sql_result"]["rows"] == [{"metric_value": 10}]
            assert turns[1]["answer"] == "结果为 20"
            assert turns[1]["sql_result"]["rows"] == [{"metric_value": 20}]
            assert turns[0]["generated_sql"] != turns[1]["generated_sql"]
        finally:
            del app.state.graph
            del app.state.checkpointer

import httpx
import pytest

from app.api.routes import chat as chat_module
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

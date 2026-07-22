import httpx
import pytest

from app.api.routes import chat as chat_module
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

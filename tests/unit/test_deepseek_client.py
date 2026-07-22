import httpx
import pytest

from app.core.config import Settings
from app.llm.deepseek import DeepSeekAnthropicClient


@pytest.mark.asyncio
async def test_parses_anthropic_compatible_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/anthropic/v1/messages"
        assert request.headers["x-api-key"] == "test-key"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": '{"sql":"SELECT 1"}'}],
                "model": "deepseek-v4-pro",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        )

    settings = Settings(llm_api_key="test-key")
    client = DeepSeekAnthropicClient(settings, transport=httpx.MockTransport(handler))
    result = await client.generate_text(system="system", user="user")

    assert result.content == '{"sql":"SELECT 1"}'
    assert result.total_tokens == 14
    assert result.model == "deepseek-v4-pro"
    assert result.latency_ms >= 0

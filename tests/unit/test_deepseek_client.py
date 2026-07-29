import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import IntegrationError
from app.llm.deepseek import DeepSeekAnthropicClient
from app.tools.models import ToolDefinition


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


@pytest.mark.asyncio
async def test_parses_openai_compatible_fallback_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"sql":"SELECT 1"}'}}],
                "model": "deepseek-v4-pro",
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            },
        )

    client = DeepSeekAnthropicClient(
        Settings(llm_api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate_text(system="system", user="user")

    assert result.content == '{"sql":"SELECT 1"}'
    assert result.total_tokens == 11


@pytest.mark.asyncio
async def test_maps_api_timeout_to_safe_integration_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = DeepSeekAnthropicClient(
        Settings(llm_api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(IntegrationError, match="DeepSeek API 请求超时"):
        await client.generate_text(system="system", user="user")


@pytest.mark.asyncio
async def test_parses_anthropic_tool_use_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tools"][0]["name"] == "render_analysis_report"
        return httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "我将生成报告。"},
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "render_analysis_report",
                        "input": {
                            "title": "第二季度退货率分析报告",
                            "sections": [
                                {"heading": "执行摘要", "content": "摘要内容"},
                                {"heading": "数据概览", "content": "数据内容"},
                                {"heading": "业务建议", "content": "建议内容"},
                            ],
                        },
                    },
                ],
                "stop_reason": "tool_use",
                "model": "deepseek-v4-pro",
                "usage": {"input_tokens": 20, "output_tokens": 30},
            },
        )

    client = DeepSeekAnthropicClient(
        Settings(_env_file=None, llm_api_key="test-key"),
        transport=httpx.MockTransport(handler),
    )
    result = await client.generate_with_tools(
        system="system",
        messages=[{"role": "user", "content": "生成报告"}],
        tools=[
            ToolDefinition(
                name="render_analysis_report",
                description="生成报告",
                input_schema={"type": "object", "properties": {}},
            )
        ],
    )

    assert result.stop_reason == "tool_use"
    assert result.total_tokens == 50
    assert result.text == "我将生成报告。"
    assert result.tool_calls[0].id == "toolu_01"
    assert result.tool_calls[0].name == "render_analysis_report"
    assert result.tool_calls[0].arguments["title"] == "第二季度退货率分析报告"

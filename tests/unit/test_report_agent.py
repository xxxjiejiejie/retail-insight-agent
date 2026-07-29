from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.llm.deepseek import LLMToolResponse
from app.tools import agent as agent_module
from app.tools.agent import handle_report_request
from app.tools.models import ToolCall, ToolDefinition, ToolResult


def report_source() -> dict[str, Any]:
    return {
        "turn_id": "turn-001",
        "intent": "sql",
        "query": "查询2026年第二季度各区域退货率",
        "answer": "华东退货率最高。",
        "generated_sql": "SELECT region, return_rate FROM metrics",
        "sql_result": {
            "columns": ["region", "return_rate"],
            "rows": [{"region": "华东", "return_rate": 3.2}],
            "row_count": 1,
        },
        "chart_spec": {
            "type": "bar",
            "title": "区域退货率",
            "x_field": "region",
            "y_field": "return_rate",
        },
    }


class FakeToolLLM:
    def __init__(self, responses: list[LLMToolResponse]):
        self.responses = responses
        self.messages: list[list[dict[str, Any]]] = []

    async def generate_with_tools(self, **kwargs: Any) -> LLMToolResponse:
        self.messages.append([dict(message) for message in kwargs["messages"]])
        return self.responses.pop(0)


class FakeRegistry:
    definitions = [
        ToolDefinition(
            name="search_policy_evidence",
            description="search",
            input_schema={"type": "object"},
        ),
        ToolDefinition(
            name="render_analysis_report",
            description="render",
            input_schema={"type": "object"},
        ),
    ]

    async def execute(self, call: ToolCall, context: Any) -> ToolResult:
        if call.name == "search_policy_evidence":
            context.policy_evidence = [{"source": "退换货制度", "excerpt": "异常需复核"}]
            return ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                status="success",
                content={"count": 1, "evidence": context.policy_evidence},
                arguments_summary={"query": "退货率", "limit": 1},
                latency_ms=4.0,
            )
        return ToolResult(
            tool_call_id=call.id,
            tool_name=call.name,
            status="success",
            content={
                "count": 1,
                "artifact": {
                    "report_id": "report-001",
                    "title": "第二季度退货率报告",
                    "format": "html",
                    "download_url": "/api/v1/reports/report-001?session_id=session-1",
                    "source_turn_id": "turn-001",
                    "created_at": "2026-07-29T00:00:00+00:00",
                },
            },
            arguments_summary={"title": "第二季度退货率报告", "section_count": 4},
            latency_ms=6.0,
        )


def tool_response(call: ToolCall, *, tokens: int = 10) -> LLMToolResponse:
    block = {
        "type": "tool_use",
        "id": call.id,
        "name": call.name,
        "input": call.arguments,
    }
    return LLMToolResponse(
        text="",
        tool_calls=(call,),
        content_blocks=(block,),
        stop_reason="tool_use",
        prompt_tokens=tokens,
        completion_tokens=5,
        latency_ms=8.0,
        model="test-model",
    )


@pytest.mark.asyncio
async def test_report_agent_runs_two_step_react_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: Settings(_env_file=None, report_max_tool_calls=2),
    )
    llm = FakeToolLLM(
        [
            tool_response(
                ToolCall(
                    id="call-search",
                    name="search_policy_evidence",
                    arguments={"query": "退货率异常处理", "limit": 1},
                )
            ),
            tool_response(
                ToolCall(
                    id="call-render",
                    name="render_analysis_report",
                    arguments={
                        "title": "第二季度退货率报告",
                        "sections": [
                            {"heading": "执行摘要", "content": "摘要"},
                            {"heading": "数据概览", "content": "概览"},
                            {"heading": "建议", "content": "建议"},
                        ],
                    },
                )
            ),
        ]
    )

    result = await handle_report_request(
        "根据结果生成报告，并补充制度依据",
        session_id="session-1",
        source_turn=report_source(),
        llm_client=llm,
        registry=FakeRegistry(),  # type: ignore[arg-type]
    )

    assert result["report_artifact"]["report_id"] == "report-001"
    assert [call["tool_name"] for call in result["tool_calls"]] == [
        "search_policy_evidence",
        "render_analysis_report",
    ]
    assert result["tool_round_count"] == 2
    assert result["metrics"]["total_tokens"] == 30
    assert result["citations"][0]["source"] == "退换货制度"
    assert len(llm.messages) == 2
    assert llm.messages[1][-1]["content"][0]["type"] == "tool_result"


@pytest.mark.asyncio
async def test_report_agent_requires_prior_structured_result() -> None:
    result = await handle_report_request(
        "生成报告",
        session_id="session-1",
        source_turn=None,
    )

    assert result["report_artifact"] is None
    assert result["clarification"]
    assert result["errors"] == ["REPORT_SOURCE_MISSING"]

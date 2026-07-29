from __future__ import annotations

from time import perf_counter
from typing import Any

from app.core.config import get_settings
from app.core.errors import ConfigurationError, IntegrationError, LLMResponseError
from app.llm.deepseek import ToolGenerator, get_llm_client
from app.tools.prompts import REPORT_AGENT_SYSTEM_PROMPT, build_report_agent_prompt
from app.tools.registry import ToolExecutionContext, ToolRegistry, build_report_tool_registry


def _failure(
    message: str,
    *,
    started: float,
    error: str,
    calls: list[dict[str, Any]] | None = None,
    results: list[dict[str, Any]] | None = None,
    rounds: int = 0,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    safe_metrics = metrics or {}
    total_tokens = int(safe_metrics.get("prompt_tokens", 0) or 0) + int(
        safe_metrics.get("completion_tokens", 0) or 0
    )
    return {
        "answer": message,
        "errors": [error],
        "tool_calls": calls or [],
        "tool_results": results or [],
        "tool_round_count": rounds,
        "report_artifact": None,
        "metrics": {
            **safe_metrics,
            "total_tokens": total_tokens,
            "tool_round_count": rounds,
            "tool_call_count": len(calls or []),
            "total_latency_ms": round((perf_counter() - started) * 1000, 2),
        },
    }


async def handle_report_request(
    request: str,
    *,
    session_id: str,
    source_turn: dict[str, Any] | None,
    llm_client: ToolGenerator | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    if source_turn is None or not source_turn.get("sql_result"):
        return {
            "clarification": "请先完成一次数据查询，再让我根据该结果生成报告。",
            **_failure(
                "当前会话中没有可用于生成报告的数据分析结果。请先查询一个经营指标。",
                started=started,
                error="REPORT_SOURCE_MISSING",
            ),
        }

    active_llm = llm_client or get_llm_client()
    active_registry = registry or build_report_tool_registry()
    execution_context = ToolExecutionContext(
        session_id=session_id,
        source_turn=source_turn,
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": build_report_agent_prompt(request, source_turn),
        }
    ]
    call_traces: list[dict[str, Any]] = []
    result_traces: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_latency_ms": 0.0,
        "tool_latency_ms": 0.0,
    }
    max_calls = get_settings().report_max_tool_calls

    for round_number in range(1, max_calls + 1):
        try:
            response = await active_llm.generate_with_tools(
                system=REPORT_AGENT_SYSTEM_PROMPT,
                messages=messages,
                tools=active_registry.definitions,
                max_tokens=1_800,
            )
        except (ConfigurationError, IntegrationError, LLMResponseError) as exc:
            return _failure(
                f"报告 Agent 暂时不可用：{exc}",
                started=started,
                error=type(exc).__name__,
                calls=call_traces,
                results=result_traces,
                rounds=round_number - 1,
                metrics=metrics,
            )

        metrics["prompt_tokens"] += response.prompt_tokens
        metrics["completion_tokens"] += response.completion_tokens
        metrics["llm_latency_ms"] = round(
            metrics["llm_latency_ms"] + response.latency_ms,
            2,
        )
        messages.append(
            {"role": "assistant", "content": list(response.content_blocks)}
        )
        remaining = max_calls - len(call_traces)
        selected_calls = list(response.tool_calls[:remaining])
        if not selected_calls:
            return _failure(
                response.text or "报告 Agent 未按要求调用报告生成工具。",
                started=started,
                error="REPORT_TOOL_NOT_CALLED",
                calls=call_traces,
                results=result_traces,
                rounds=round_number,
                metrics=metrics,
            )

        tool_blocks: list[dict[str, Any]] = []
        for call in selected_calls:
            result = await active_registry.execute(call, execution_context)
            trace = result.to_trace()
            call_traces.append(
                {
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "arguments_summary": trace["arguments_summary"],
                }
            )
            result_traces.append(trace)
            metrics["tool_latency_ms"] = round(
                metrics["tool_latency_ms"] + result.latency_ms,
                2,
            )
            tool_blocks.append(result.to_anthropic_block())
            artifact = result.content.get("artifact")
            if result.status == "success" and isinstance(artifact, dict):
                metrics["total_tokens"] = (
                    metrics["prompt_tokens"] + metrics["completion_tokens"]
                )
                metrics["tool_round_count"] = round_number
                metrics["tool_call_count"] = len(call_traces)
                metrics["total_latency_ms"] = round(
                    (perf_counter() - started) * 1000,
                    2,
                )
                return {
                    "answer": (
                        f"报告《{artifact.get('title', '经营分析报告')}》已生成。"
                        "完整内容和数据来源已写入报告文件。"
                    ),
                    "citations": execution_context.policy_evidence,
                    "errors": [],
                    "tool_calls": call_traces,
                    "tool_results": result_traces,
                    "tool_round_count": round_number,
                    "report_artifact": artifact,
                    "metrics": metrics,
                }

        messages.append({"role": "user", "content": tool_blocks})

    return _failure(
        "报告 Agent 已达到工具调用上限，未能生成报告。",
        started=started,
        error="REPORT_TOOL_LIMIT_REACHED",
        calls=call_traces,
        results=result_traces,
        rounds=max_calls,
        metrics=metrics,
    )

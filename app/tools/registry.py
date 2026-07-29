from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.observability.langsmith import observe_chain
from app.tools.models import (
    RenderAnalysisReportArgs,
    SearchPolicyEvidenceArgs,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from app.tools.reporting import render_analysis_report, search_policy_evidence

ToolHandler = Callable[[BaseModel, "ToolExecutionContext"], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ToolExecutionContext:
    session_id: str
    source_turn: dict[str, Any]
    policy_evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ToolSpec:
    definition: ToolDefinition
    arguments_model: type[BaseModel]
    handler: ToolHandler
    tags: tuple[str, ...]


def _definition(
    name: str,
    description: str,
    arguments_model: type[BaseModel],
) -> ToolDefinition:
    schema = arguments_model.model_json_schema()
    schema.pop("title", None)
    return ToolDefinition(name=name, description=description, input_schema=schema)


def _arguments_summary(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "search_policy_evidence":
        query = str(arguments.get("query", ""))
        return {"query": query[:80], "limit": arguments.get("limit", 3)}
    if name == "render_analysis_report":
        sections = arguments.get("sections", [])
        return {
            "title": str(arguments.get("title", ""))[:80],
            "report_type": arguments.get("report_type"),
            "include_chart": arguments.get("include_chart"),
            "section_count": len(sections) if isinstance(sections, list) else 0,
        }
    return {}


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]):
        self._specs = {spec.definition.name: spec for spec in specs}

    @property
    def definitions(self) -> list[ToolDefinition]:
        return [spec.definition for spec in self._specs.values()]

    async def execute(
        self,
        call: ToolCall,
        context: ToolExecutionContext,
    ) -> ToolResult:
        started = perf_counter()
        summary = _arguments_summary(call.name, call.arguments)
        spec = self._specs.get(call.name)
        if spec is None:
            return ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                status="error",
                content={"message": "该工具不在允许的白名单中。"},
                arguments_summary=summary,
                error_type="unknown_tool",
            )
        try:
            validated = spec.arguments_model.model_validate(call.arguments)
        except ValidationError:
            return ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                status="error",
                content={"message": "工具参数未通过安全校验。"},
                arguments_summary=summary,
                latency_ms=round((perf_counter() - started) * 1000, 2),
                error_type="invalid_arguments",
            )

        try:
            async with observe_chain(
                f"tool.{call.name}",
                inputs={"tool_name": call.name, "arguments_summary": summary},
                tags=["tool", *spec.tags],
                metadata={"tool_name": call.name, "status": "running"},
            ) as span:
                content = await asyncio.wait_for(
                    spec.handler(validated, context),
                    timeout=get_settings().report_tool_timeout_seconds,
                )
                latency_ms = round((perf_counter() - started) * 1000, 2)
                result = ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    status="success",
                    content=content,
                    arguments_summary=summary,
                    latency_ms=latency_ms,
                )
                await span.end(result.to_trace())
                return result
        except TimeoutError:
            error_type = "timeout"
            message = "工具执行超时，请稍后重试。"
        except Exception:
            error_type = "execution_error"
            message = "工具暂时不可用，未返回内部错误信息。"
        return ToolResult(
            tool_call_id=call.id,
            tool_name=call.name,
            status="error",
            content={"message": message},
            arguments_summary=summary,
            latency_ms=round((perf_counter() - started) * 1000, 2),
            error_type=error_type,
        )


def build_report_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                definition=_definition(
                    "search_policy_evidence",
                    "检索与报告主题相关的制度证据。仅在报告需要制度依据或合规建议时调用。",
                    SearchPolicyEvidenceArgs,
                ),
                arguments_model=SearchPolicyEvidenceArgs,
                handler=search_policy_evidence,
                tags=("readonly", "policy"),
            ),
            ToolSpec(
                definition=_definition(
                    "render_analysis_report",
                    "将结构化章节渲染为安全的 HTML 分析报告。报告必须通过此工具生成。",
                    RenderAnalysisReportArgs,
                ),
                arguments_model=RenderAnalysisReportArgs,
                handler=render_analysis_report,
                tags=("artifact", "report"),
            ),
        ]
    )

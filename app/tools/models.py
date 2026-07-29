from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolDefinition(StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]


class ToolCall(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(StrictModel):
    tool_call_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=64)
    status: Literal["success", "error"]
    content: dict[str, Any] = Field(default_factory=dict)
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = Field(default=0.0, ge=0)
    error_type: str | None = Field(default=None, max_length=80)

    def to_trace(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "result_count": self.content.get("count"),
        }

    def to_anthropic_block(self) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_call_id,
            "content": json.dumps(self.content, ensure_ascii=False, default=str),
            "is_error": self.status == "error",
        }


class SearchPolicyEvidenceArgs(StrictModel):
    query: str = Field(min_length=2, max_length=200)
    limit: int = Field(default=3, ge=1, le=5)


class ReportSection(StrictModel):
    heading: str = Field(min_length=2, max_length=80)
    content: str = Field(min_length=2, max_length=3_000)


class RenderAnalysisReportArgs(StrictModel):
    title: str = Field(min_length=4, max_length=120)
    report_type: Literal["analysis", "executive_summary"] = "analysis"
    include_chart: bool = True
    sections: list[ReportSection] = Field(min_length=3, max_length=8)


class ReportArtifact(StrictModel):
    report_id: str
    title: str
    format: Literal["html"] = "html"
    download_url: str
    source_turn_id: str
    created_at: datetime

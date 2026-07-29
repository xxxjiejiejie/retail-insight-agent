from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.tools import registry as registry_module
from app.tools import reporting
from app.tools.models import (
    RenderAnalysisReportArgs,
    ReportSection,
    SearchPolicyEvidenceArgs,
    ToolCall,
    ToolDefinition,
)
from app.tools.registry import ToolExecutionContext, ToolRegistry, ToolSpec


def source_turn() -> dict:
    return {
        "turn_id": "turn-source-1",
        "query": "查询第二季度各区域退货率",
        "generated_sql": "SELECT region, return_rate FROM report_source",
        "sql_result": {
            "columns": ["region", "return_rate"],
            "rows": [
                {"region": "华东<script>", "return_rate": 3.2},
                {"region": "华南", "return_rate": 2.1},
            ],
            "row_count": 2,
            "execution_ms": 2.0,
            "executed_sql": "SELECT region, return_rate FROM report_source",
        },
        "chart_spec": {
            "type": "bar",
            "title": "区域退货率",
            "x_field": "region",
            "y_field": "return_rate",
        },
    }


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool() -> None:
    registry = registry_module.build_report_tool_registry()
    result = await registry.execute(
        ToolCall(id="call-1", name="run_shell", arguments={"command": "whoami"}),
        ToolExecutionContext(session_id="session-1", source_turn=source_turn()),
    )

    assert result.status == "error"
    assert result.error_type == "unknown_tool"
    assert "command" not in result.arguments_summary


@pytest.mark.asyncio
async def test_registry_rejects_extra_arguments() -> None:
    registry = registry_module.build_report_tool_registry()
    result = await registry.execute(
        ToolCall(
            id="call-2",
            name="search_policy_evidence",
            arguments={"query": "退换货", "limit": 2, "path": "C:/private"},
        ),
        ToolExecutionContext(session_id="session-1", source_turn=source_turn()),
    )

    assert result.status == "error"
    assert result.error_type == "invalid_arguments"
    assert "path" not in result.arguments_summary


@pytest.mark.asyncio
async def test_registry_maps_timeout_to_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyArgs(BaseModel):
        pass

    async def slow_handler(_: BaseModel, __: ToolExecutionContext) -> dict:
        raise TimeoutError

    spec = ToolSpec(
        definition=ToolDefinition(
            name="slow_tool",
            description="slow",
            input_schema={"type": "object", "properties": {}},
        ),
        arguments_model=EmptyArgs,
        handler=slow_handler,
        tags=("test",),
    )
    monkeypatch.setattr(
        registry_module,
        "get_settings",
        lambda: Settings(_env_file=None, report_tool_timeout_seconds=0.1),
    )
    result = await ToolRegistry([spec]).execute(
        ToolCall(id="call-3", name="slow_tool", arguments={}),
        ToolExecutionContext(session_id="session-1", source_turn=source_turn()),
    )

    assert result.status == "error"
    assert result.error_type == "timeout"
    assert "内部" not in result.content["message"]


@pytest.mark.asyncio
async def test_report_renderer_escapes_content_and_binds_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        report_output_path=str(tmp_path),
        api_prefix="/api/v1",
    )
    monkeypatch.setattr(reporting, "get_settings", lambda: settings)
    context = ToolExecutionContext(
        session_id="safe-session",
        source_turn=source_turn(),
        policy_evidence=[
            {
                "source": "退换货制度",
                "version": "1.0",
                "section": "异常处理",
                "excerpt": "不得执行 <script>alert(1)</script>",
            }
        ],
    )
    args = RenderAnalysisReportArgs(
        title="第二季度退货率分析报告",
        sections=[
            ReportSection(heading="执行摘要", content="华东需要关注<script>"),
            ReportSection(heading="数据概览", content="共返回两个区域"),
            ReportSection(heading="业务建议", content="复核退货原因"),
        ],
    )

    result = await reporting.render_analysis_report(args, context)
    artifact = result["artifact"]
    report_path = tmp_path / f"{artifact['report_id']}.html"
    metadata_path = tmp_path / f"{artifact['report_id']}.json"
    html = report_path.read_text(encoding="utf-8")

    assert report_path.is_file()
    assert metadata_path.is_file()
    assert "safe-session" in artifact["download_url"]
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "华东&lt;script&gt;" in html


def test_tool_argument_models_forbid_extra_fields() -> None:
    with pytest.raises(ValueError):
        SearchPolicyEvidenceArgs.model_validate(
            {"query": "退换货", "limit": 3, "sql": "SELECT secret"}
        )


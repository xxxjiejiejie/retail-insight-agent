"""Run deterministic failure-recovery demonstrations without external model calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from app.core.errors import DatabaseQueryError, IntegrationError
from app.database.engine import get_business_engine
from app.llm.deepseek import LLMTextResponse
from app.sql_agent.service import handle_sql_question

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "resilience_eval_report.json"
VALID_PLAN = (
    '{"sql":"SELECT region, COUNT(*) AS store_count FROM stores GROUP BY region",'
    '"explanation":"统计区域门店数","chart":null}'
)


class SequenceGenerator:
    def __init__(self, responses: list[LLMTextResponse | Exception]):
        self.responses = responses

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _entry(
    case_id: str,
    title: str,
    result: dict[str, Any],
    *,
    passed: bool,
    recovery: str,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "set_type": "resilience",
        "category": "failure_recovery",
        "branch": "sql",
        "question": title,
        "passed": passed,
        "recovery": recovery,
        "answer": result.get("answer"),
        "errors": result.get("errors", []),
        "metrics": result.get("metrics", {}),
    }


async def evaluate() -> list[dict[str, Any]]:
    engine = get_business_engine()
    try:
        timeout_result = await handle_sql_question(
            "各区域有多少家门店？",
            llm_client=SequenceGenerator([IntegrationError("DeepSeek API 请求超时")]),
            engine=engine,
        )
        format_result = await handle_sql_question(
            "各区域有多少家门店？",
            llm_client=SequenceGenerator(
                [
                    LLMTextResponse("not-json", 10, 2, latency_ms=5),
                    LLMTextResponse(VALID_PLAN, 20, 6, latency_ms=8),
                ]
            ),
            engine=engine,
        )
        database_generator = SequenceGenerator(
            [LLMTextResponse(VALID_PLAN, 10, 5, latency_ms=3) for _ in range(3)]
        )
        with patch(
            "app.sql_agent.service.execute_read_only_sql",
            new=AsyncMock(side_effect=DatabaseQueryError("SQL 查询超过时间限制")),
        ):
            database_result = await handle_sql_question(
                "各区域有多少家门店？",
                llm_client=database_generator,
                engine=engine,
            )
    finally:
        await engine.dispose()

    report = [
        _entry(
            "RES-001",
            "LLM API 超时安全降级",
            timeout_result,
            passed=(
                timeout_result.get("errors") == ["IntegrationError"]
                and "请求超时" in str(timeout_result.get("answer"))
                and "Traceback" not in str(timeout_result.get("answer"))
            ),
            recovery="返回统一安全错误，不泄露连接信息或堆栈。",
        ),
        _entry(
            "RES-002",
            "LLM 格式异常自动修复",
            format_result,
            passed=(
                not format_result.get("errors")
                and format_result.get("sql_result") is not None
                and format_result.get("metrics", {}).get("attempt_count") == 2
            ),
            recovery="首次非 JSON 输出触发修复 Prompt，第二次生成并执行成功。",
        ),
        _entry(
            "RES-003",
            "数据库超时安全失败",
            database_result,
            passed=(
                database_result.get("errors") == ["DatabaseQueryError"]
                and database_result.get("metrics", {}).get("attempt_count") == 3
                and "Traceback" not in str(database_result.get("answer"))
            ),
            recovery="按既定重试上限结束，返回统一数据库超时错误。",
        ),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def main() -> None:
    report = await evaluate()
    passed = sum(bool(entry["passed"]) for entry in report)
    for entry in report:
        print(f"{entry['id']} passed={str(entry['passed']).lower()}")
    print(f"summary={passed}/{len(report)} report={REPORT_PATH}")
    if passed != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

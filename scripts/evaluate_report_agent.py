"""Evaluate the live multi-turn report Agent through the public API.

This script intentionally requires --live because both turns can invoke the configured
LLM API. It sends only the synthetic questions in data/eval/report_agent_cases.json and
the application's own bounded analysis result to the configured model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "report_agent_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "report_agent_eval_report.json"


async def evaluate_case(
    client: httpx.AsyncClient,
    case: dict,
    *,
    session_id: str,
) -> dict:
    source_response = await client.post(
        "/api/v1/chat",
        json={"query": case["source_query"], "session_id": session_id},
    )
    source_payload = source_response.json()
    report_response = await client.post(
        "/api/v1/chat",
        json={"query": case["followup"], "session_id": session_id},
    )
    payload = report_response.json()
    tool_names = [item.get("tool_name") for item in payload.get("tool_results", [])]
    expected = case["expected_tools"]
    passed = (
        source_response.is_success
        and report_response.is_success
        and payload.get("intent") == "report"
        and bool(payload.get("report_artifact"))
        and not payload.get("errors")
        and all(name in tool_names for name in expected)
        and len(tool_names) <= 2
    )
    return {
        "id": case["id"],
        "passed": passed,
        "source_status": source_response.status_code,
        "report_status": report_response.status_code,
        "source_intent": source_payload.get("intent"),
        "report_intent": payload.get("intent"),
        "expected_tools": expected,
        "actual_tools": tool_names,
        "tool_round_count": payload.get("tool_round_count", 0),
        "total_tokens": payload.get("metrics", {}).get("total_tokens", 0),
        "latency_ms": payload.get("metrics", {}).get("total_latency_ms"),
        "errors": payload.get("errors", []),
    }


async def run(base_url: str, cases: list[dict]) -> list[dict]:
    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        results: list[dict] = []
        for case in cases:
            session_id = f"report-eval-{uuid4()}"
            results.append(await evaluate_case(client, case, session_id=session_id))
            result = results[-1]
            print(
                f"{result['id']} passed={str(result['passed']).lower()} "
                f"tools={','.join(result['actual_tools']) or '-'} "
                f"tokens={result['total_tokens']}"
            )
        return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="确认允许调用配置的真实模型 API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--case-id", action="append", default=[])
    args = parser.parse_args()
    if not args.live:
        raise SystemExit(
            "该脚本会产生真实模型调用；请在确认外发内容后显式添加 --live。"
        )
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["id"] in selected]
        if len(cases) != len(selected):
            raise SystemExit("存在未知 case_id。")
    results = asyncio.run(run(args.base_url, cases))
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "total": len(results),
        "passed": sum(bool(item["passed"]) for item in results),
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary={report['passed']}/{report['total']} report={REPORT_PATH}")
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

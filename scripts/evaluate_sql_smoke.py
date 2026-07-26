"""Evaluate DeepSeek-generated SQL by comparing database result values."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.evaluation.metrics import result_values_match
from app.sql_agent.executor import execute_read_only_sql
from app.sql_agent.service import handle_sql_question

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "sql_smoke_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only a selected case; may be passed more than once.",
    )
    parser.add_argument(
        "--reuse-generated",
        action="store_true",
        help="Reuse SQL from the prior report and make no LLM requests.",
    )
    return parser.parse_args()


async def evaluate(
    case_ids: set[str] | None = None,
    *,
    reuse_generated: bool = False,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    selected = [case for case in cases if case_ids is None or case["id"] in case_ids]
    if not selected:
        raise SystemExit("No SQL smoke cases matched the requested IDs")

    prior_by_id: dict[str, dict[str, Any]] = {}
    if reuse_generated:
        if not REPORT_PATH.exists():
            raise SystemExit("No prior SQL smoke report is available")
        prior_report: list[dict[str, Any]] = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        prior_by_id = {entry["id"]: entry for entry in prior_report}

    engine = get_business_engine()
    report: list[dict[str, Any]] = []
    try:
        schema = await load_schema_catalog(engine)
        for case in selected:
            if reuse_generated:
                prior = prior_by_id.get(case["id"])
                if prior is None:
                    raise SystemExit(f"No prior report entry for {case['id']}")
                prior_sql = prior.get("generated_sql")
                if not isinstance(prior_sql, str) or not prior_sql:
                    raise SystemExit(f"No prior generated SQL for {case['id']}")
                local_result = await execute_read_only_sql(prior_sql, schema, engine=engine)
                generated = {**prior, "sql_result": asdict(local_result)}
            else:
                generated = await handle_sql_question(case["question"], engine=engine)
            generated_result = generated.get("sql_result")
            reference = await execute_read_only_sql(case["reference_sql"], schema, engine=engine)
            passed = bool(
                generated_result
                and result_values_match(
                    generated_result["rows"],
                    reference.rows,
                    comparison=case.get("comparison"),
                )
            )
            entry = {
                "id": case["id"],
                "question": case["question"],
                "passed": passed,
                "generated_sql": generated.get("generated_sql"),
                "generated_row_count": (
                    generated_result.get("row_count") if generated_result else None
                ),
                "reference_row_count": reference.row_count,
                "answer": generated.get("answer"),
                "metrics": generated.get("metrics", {}),
                "errors": generated.get("errors", []),
                "reused_generated_sql": reuse_generated,
            }
            report.append(entry)
            print(
                f"{case['id']} passed={str(passed).lower()} "
                f"attempts={entry['metrics'].get('attempt_count', 0)} "
                f"tokens={entry['metrics'].get('total_tokens', 0)}"
            )
    finally:
        await engine.dispose()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


async def main() -> None:
    args = parse_args()
    report = await evaluate(
        set(args.case_ids) if args.case_ids else None,
        reuse_generated=args.reuse_generated,
    )
    passed_count = sum(1 for entry in report if entry["passed"])
    print(f"summary={passed_count}/{len(report)} report={REPORT_PATH}")
    if passed_count != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

"""Evaluate five real DeepSeek Hybrid questions against SQL results and citations."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.evaluation.metrics import result_values_match
from app.graph.nodes import hybrid_node
from app.sql_agent.executor import execute_read_only_sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HYBRID_CASES_PATH = PROJECT_ROOT / "data" / "eval" / "hybrid_cases.json"
SQL_CASES_PATH = PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "hybrid_live_report.json"
DEFAULT_CASE_IDS = {
    "HYBRID-001",
    "HYBRID-002",
    "HYBRID-003",
    "HYBRID-006",
    "HYBRID-007",
}


def report_path_for(case_ids: set[str]) -> Path:
    """Keep focused reruns from overwriting the five-case baseline report."""
    if case_ids == DEFAULT_CASE_IDS:
        return REPORT_PATH
    suffix = "_".join(case_id.lower().replace("-", "_") for case_id in sorted(case_ids))
    return REPORT_PATH.with_name(f"hybrid_live_{suffix}_report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run selected Hybrid cases; defaults to five reference-backed cases.",
    )
    return parser.parse_args()


async def evaluate(case_ids: set[str]) -> tuple[list[dict[str, Any]], Path]:
    hybrid_cases: list[dict[str, Any]] = json.loads(
        HYBRID_CASES_PATH.read_text(encoding="utf-8")
    )
    sql_cases: list[dict[str, str]] = json.loads(
        SQL_CASES_PATH.read_text(encoding="utf-8")
    )
    references = {case["id"]: case["reference_sql"] for case in sql_cases}
    selected = [case for case in hybrid_cases if case["id"] in case_ids]
    if len(selected) != len(case_ids):
        available = {case["id"] for case in hybrid_cases}
        missing = sorted(case_ids - available)
        raise SystemExit(f"Unknown Hybrid case IDs: {', '.join(missing)}")

    engine = get_business_engine()
    report: list[dict[str, Any]] = []
    try:
        schema = await load_schema_catalog(engine)
        for case in selected:
            reference_id = case.get("reference_sql_case_id")
            if reference_id not in references:
                raise SystemExit(f"{case['id']} has no valid reference_sql_case_id")

            result = await hybrid_node({"user_query": case["query"]})
            generated_result = result.get("sql_result")
            reference_result = await execute_read_only_sql(
                references[reference_id],
                schema,
                engine=engine,
            )
            sql_passed = bool(
                generated_result
                and result_values_match(generated_result["rows"], reference_result.rows)
            )
            cited_ids = {
                citation.get("document_id")
                for citation in result.get("citations", [])
                if citation.get("document_id")
            }
            expected_ids = set(case["expected_document_ids"])
            citation_passed = expected_ids <= cited_ids
            passed = sql_passed and citation_passed and not result.get("errors")
            entry = {
                "id": case["id"],
                "question": case["query"],
                "passed": passed,
                "sql_passed": sql_passed,
                "citation_passed": citation_passed,
                "reference_sql_case_id": reference_id,
                "generated_sql": result.get("generated_sql"),
                "generated_row_count": (
                    generated_result.get("row_count") if generated_result else None
                ),
                "reference_row_count": reference_result.row_count,
                "expected_document_ids": sorted(expected_ids),
                "cited_document_ids": sorted(cited_ids),
                "answer": result.get("answer"),
                "errors": result.get("errors", []),
                "metrics": result.get("metrics", {}),
            }
            report.append(entry)
            print(
                f"{case['id']} passed={str(passed).lower()} "
                f"sql={str(sql_passed).lower()} citations={str(citation_passed).lower()} "
                f"tokens={entry['metrics'].get('total_tokens', 0)}"
            )
    finally:
        await engine.dispose()

    report_path = report_path_for(case_ids)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report, report_path


async def main() -> None:
    args = parse_args()
    case_ids = set(args.case_ids) if args.case_ids else DEFAULT_CASE_IDS
    report, report_path = await evaluate(case_ids)
    passed_count = sum(entry["passed"] for entry in report)
    total_tokens = sum(entry["metrics"].get("total_tokens", 0) for entry in report)
    print(
        f"summary={passed_count}/{len(report)} total_tokens={total_tokens} "
        f"report={report_path}"
    )
    if passed_count != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

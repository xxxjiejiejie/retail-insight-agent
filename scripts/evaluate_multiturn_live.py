"""Run real two-turn SQL, RAG, and Hybrid follow-up evaluations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.evaluation.metrics import result_values_match
from app.graph.workflow import build_graph
from app.sql_agent.executor import execute_read_only_sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "conversation_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "multiturn_live_report.json"
INFRASTRUCTURE_ERRORS = {
    "ConfigurationError",
    "DatabaseQueryError",
    "IntegrationError",
    "LLM_API_KEY_NOT_CONFIGURED",
    "LLMResponseError",
}


def _pair_metrics(base: dict[str, Any], followup: dict[str, Any]) -> dict[str, Any]:
    raw_base_metrics = base.get("metrics")
    raw_followup_metrics = followup.get("metrics")
    base_metrics: dict[str, Any] = (
        raw_base_metrics if isinstance(raw_base_metrics, dict) else {}
    )
    followup_metrics: dict[str, Any] = (
        raw_followup_metrics if isinstance(raw_followup_metrics, dict) else {}
    )

    def metric_value(metrics: dict[str, Any], key: str) -> float:
        value = metrics.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0

    merged = dict(followup_metrics)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "llm_latency_ms"):
        merged[key] = round(
            metric_value(base_metrics, key) + metric_value(followup_metrics, key),
            2,
        )
    merged["total_latency_ms"] = round(
        metric_value(base_metrics, "total_latency_ms")
        + metric_value(followup_metrics, "total_latency_ms"),
        2,
    )
    merged["context_used"] = bool(followup.get("context_used"))
    return merged


async def evaluate() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    graph = build_graph()
    engine = get_business_engine()
    report: list[dict[str, Any]] = []
    try:
        schema = await load_schema_catalog(engine)
        for case in cases:
            base = await graph.ainvoke({"user_query": case["base_question"], "turns": []})
            followup = await graph.ainvoke(
                {
                    "user_query": case["followup_question"],
                    "turns": base.get("turns", []),
                }
            )
            branch = str(case["branch"])
            errors = [str(error) for error in followup.get("errors", [])]
            context_passed = bool(followup.get("context_used"))
            intent_passed = followup.get("intent") == branch
            sql_passed = True
            reference_row_count: int | None = None
            generated_row_count: int | None = None
            if isinstance(case.get("reference_sql"), str):
                reference = await execute_read_only_sql(
                    case["reference_sql"], schema, engine=engine
                )
                reference_row_count = reference.row_count
                generated_result = followup.get("sql_result")
                generated_row_count = (
                    generated_result.get("row_count")
                    if isinstance(generated_result, dict)
                    else None
                )
                sql_passed = bool(
                    isinstance(generated_result, dict)
                    and result_values_match(
                        generated_result.get("rows", []),
                        reference.rows,
                        comparison=case.get("comparison"),
                    )
                )
            cited_ids = sorted(
                {
                    str(citation["document_id"])
                    for citation in followup.get("citations", [])
                    if isinstance(citation, dict) and citation.get("document_id")
                }
            )
            expected_ids = {str(value) for value in case.get("expected_document_ids", [])}
            citation_passed = expected_ids <= set(cited_ids)
            infrastructure_ok = not INFRASTRUCTURE_ERRORS.intersection(errors)
            passed = (
                context_passed
                and intent_passed
                and sql_passed
                and citation_passed
                and infrastructure_ok
            )
            entry = {
                "id": case["id"],
                "set_type": "multi_turn",
                "category": f"multi_turn_{branch}",
                "branch": branch,
                "base_question": case["base_question"],
                "question": case["followup_question"],
                "resolved_query": followup.get("resolved_query"),
                "passed": passed,
                "context_passed": context_passed,
                "intent_passed": intent_passed,
                "sql_passed": sql_passed,
                "citation_passed": citation_passed,
                "expected_document_ids": sorted(expected_ids),
                "cited_document_ids": cited_ids,
                "generated_sql": followup.get("generated_sql"),
                "generated_row_count": generated_row_count,
                "reference_row_count": reference_row_count,
                "answer": followup.get("answer"),
                "errors": errors,
                "metrics": _pair_metrics(base, followup),
            }
            report.append(entry)
            print(
                f"{case['id']} branch={branch} passed={str(passed).lower()} "
                f"context={str(context_passed).lower()}"
            )
    finally:
        await engine.dispose()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def main() -> None:
    report = await evaluate()
    passed = sum(bool(entry["passed"]) for entry in report)
    print(f"summary={passed}/{len(report)} report={REPORT_PATH}")
    if passed != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

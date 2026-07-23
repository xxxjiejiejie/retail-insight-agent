"""Run the unified 100-case local evaluation without paid LLM requests."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.config import get_settings
from app.core.errors import RetailInsightError
from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.evaluation.suite import (
    EvaluationResult,
    evaluate_hybrid_cases,
    evaluate_router_cases,
    evaluate_safety_cases,
    summarize_results,
)
from app.rag.runtime import get_policy_reranker, get_policy_retriever
from app.sql_agent.executor import execute_read_only_sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "comprehensive_eval_report.json"
QUICK_REPORT_PATH = (
    PROJECT_ROOT / "data" / "runtime" / "comprehensive_eval_quick_report.json"
)


def load_json(name: str) -> Any:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def evaluate_fast_cases() -> list[EvaluationResult]:
    return [
        *evaluate_router_cases(load_json("router_cases.json")),
        *evaluate_hybrid_cases(load_json("hybrid_cases.json")),
        *evaluate_safety_cases(load_json("sql_safety_cases.json")),
    ]


async def evaluate_sql_references() -> list[EvaluationResult]:
    cases: list[dict[str, str]] = load_json("sql_smoke_cases.json")
    engine = get_business_engine()
    results: list[EvaluationResult] = []
    try:
        schema = await load_schema_catalog(engine)
        for case in cases:
            try:
                query_result = await execute_read_only_sql(
                    case["reference_sql"],
                    schema,
                    engine=engine,
                )
                results.append(
                    EvaluationResult(
                        case_id=case["id"],
                        category="sql_reference",
                        passed=True,
                        details={"row_count": query_result.row_count},
                    )
                )
            except RetailInsightError as exc:
                results.append(
                    EvaluationResult(
                        case_id=case["id"],
                        category="sql_reference",
                        passed=False,
                        details={"error_type": type(exc).__name__, "error": str(exc)},
                    )
                )
    finally:
        await engine.dispose()
    return results


async def evaluate_rag_retrieval() -> list[EvaluationResult]:
    cases: list[dict[str, Any]] = load_json("rag_cases.json")
    settings = get_settings()
    retriever = get_policy_retriever()
    reranker = get_policy_reranker()
    results: list[EvaluationResult] = []
    for case in cases:
        try:
            candidates = await retriever.retrieve(
                case["question"],
                top_k=settings.rag_retrieval_top_k,
            )
            ranked = await reranker.rerank(
                case["question"],
                candidates,
                top_k=settings.rag_rerank_top_k,
            )
            evidence = [
                item for item in ranked if item.score >= settings.rag_min_relevance_score
            ]
            actual_ids = {item.chunk.document_id for item in evidence}
            expected_ids = set(case["expected_document_ids"])
            passed = (
                expected_ids <= actual_ids if case["expect_answer"] else not evidence
            )
            details = {
                "expect_answer": case["expect_answer"],
                "expected_document_ids": sorted(expected_ids),
                "actual_document_ids": sorted(actual_ids),
                "top_scores": [round(item.score, 6) for item in ranked],
            }
        except RetailInsightError as exc:
            passed = False
            details = {"error_type": type(exc).__name__, "error": str(exc)}
        results.append(
            EvaluationResult(
                case_id=case["id"],
                category="rag_retrieval",
                passed=passed,
                details=details,
            )
        )
    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only 50 routing, Hybrid splitting, and SQL safety cases.",
    )
    args = parser.parse_args()
    started = perf_counter()
    results = evaluate_fast_cases()
    if not args.quick:
        results.extend(await evaluate_sql_references())
        results.extend(await evaluate_rag_retrieval())

    summary = summarize_results(results)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "quick" if args.quick else "full_local",
        "paid_llm_calls": 0,
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "summary": summary,
        "results": [result.to_dict() for result in results],
    }
    report_path = QUICK_REPORT_PATH if args.quick else REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"mode={report['mode']} passed={summary['passed']}/{summary['total']} "
        f"duration_ms={report['duration_ms']} paid_llm_calls=0"
    )
    for category, category_summary in summary["categories"].items():
        print(
            f"category={category} passed={category_summary['passed']}/"
            f"{category_summary['total']} pass_rate={category_summary['pass_rate']:.2%}"
        )
    print(f"report={report_path}")
    if summary["passed"] != summary["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

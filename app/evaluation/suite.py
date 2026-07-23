from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from app.graph.nodes import split_hybrid_query
from app.graph.router import classify_intent
from app.sql_agent.validator import validate_read_only_sql


@dataclass(slots=True, frozen=True)
class EvaluationResult:
    case_id: str
    category: str
    passed: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_router_cases(cases: list[dict[str, Any]]) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        actual = classify_intent(str(case["query"]))
        expected = str(case["expected_intent"])
        results.append(
            EvaluationResult(
                case_id=str(case["id"]),
                category="router",
                passed=actual == expected,
                details={"expected_intent": expected, "actual_intent": actual},
            )
        )
    return results


def evaluate_hybrid_cases(cases: list[dict[str, Any]]) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for case in cases:
        query = str(case["query"])
        actual_intent = classify_intent(query)
        sql_query, rag_query = split_hybrid_query(query)
        missing_sql = [term for term in case["sql_contains"] if term not in sql_query]
        missing_rag = [term for term in case["rag_contains"] if term not in rag_query]
        passed = actual_intent == "hybrid" and not missing_sql and not missing_rag
        results.append(
            EvaluationResult(
                case_id=str(case["id"]),
                category="hybrid_split",
                passed=passed,
                details={
                    "actual_intent": actual_intent,
                    "sql_query": sql_query,
                    "rag_query": rag_query,
                    "missing_sql_terms": missing_sql,
                    "missing_rag_terms": missing_rag,
                    "expected_document_ids": case["expected_document_ids"],
                },
            )
        )
    return results


def evaluate_safety_cases(payload: dict[str, Any]) -> list[EvaluationResult]:
    allowed_columns = {
        str(table): {str(column) for column in columns}
        for table, columns in payload["allowed_columns"].items()
    }
    results: list[EvaluationResult] = []
    for case in payload["cases"]:
        validation = validate_read_only_sql(
            str(case["sql"]),
            allowed_tables=set(allowed_columns),
            allowed_columns=allowed_columns,
        )
        expected_safe = bool(case["expected_safe"])
        expected_error = case.get("expected_error")
        error_matched = expected_error is None or any(
            str(expected_error) in error for error in validation.errors
        )
        results.append(
            EvaluationResult(
                case_id=str(case["id"]),
                category="sql_safety",
                passed=validation.is_safe == expected_safe and error_matched,
                details={
                    "expected_safe": expected_safe,
                    "actual_safe": validation.is_safe,
                    "expected_error": expected_error,
                    "errors": validation.errors,
                },
            )
        )
    return results


def summarize_results(results: Iterable[EvaluationResult]) -> dict[str, Any]:
    materialized = list(results)
    totals = Counter(result.category for result in materialized)
    passed = Counter(result.category for result in materialized if result.passed)
    category_summary = {
        category: {
            "passed": passed[category],
            "total": total,
            "pass_rate": round(passed[category] / total, 4) if total else 0.0,
        }
        for category, total in sorted(totals.items())
    }
    passed_count = sum(result.passed for result in materialized)
    total_count = len(materialized)
    return {
        "passed": passed_count,
        "total": total_count,
        "pass_rate": round(passed_count / total_count, 4) if total_count else 0.0,
        "categories": category_summary,
        "failed_case_ids": [result.case_id for result in materialized if not result.passed],
    }

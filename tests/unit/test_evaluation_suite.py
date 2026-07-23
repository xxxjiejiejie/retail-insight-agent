from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.suite import (
    EvaluationResult,
    evaluate_hybrid_cases,
    evaluate_router_cases,
    evaluate_safety_cases,
    summarize_results,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"


def load_json(name: str) -> object:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def test_all_router_evaluation_cases_pass() -> None:
    cases = load_json("router_cases.json")
    assert isinstance(cases, list)

    results = evaluate_router_cases(cases)

    assert len(results) == 25
    assert all(result.passed for result in results)


def test_all_hybrid_split_cases_pass() -> None:
    cases = load_json("hybrid_cases.json")
    assert isinstance(cases, list)

    results = evaluate_hybrid_cases(cases)

    assert len(results) == 10
    assert all(result.passed for result in results)


def test_all_sql_safety_cases_pass() -> None:
    payload = load_json("sql_safety_cases.json")
    assert isinstance(payload, dict)

    results = evaluate_safety_cases(payload)

    assert len(results) == 15
    assert all(result.passed for result in results)


def test_summary_groups_failures_by_category() -> None:
    results = [
        EvaluationResult("ONE", "router", True, {}),
        EvaluationResult("TWO", "router", False, {}),
        EvaluationResult("THREE", "sql_safety", True, {}),
    ]

    summary = summarize_results(results)

    assert summary["passed"] == 2
    assert summary["total"] == 3
    assert summary["categories"]["router"]["pass_rate"] == 0.5
    assert summary["failed_case_ids"] == ["TWO"]

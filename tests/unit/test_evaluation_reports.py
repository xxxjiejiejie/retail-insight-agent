import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.evaluation.reports import (
    build_evaluation_run,
    load_evaluation_run,
    load_evaluation_runs,
    save_evaluation_run,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _build_fixture_run(tmp_path: Path) -> dict:
    runtime = tmp_path / "runtime"
    eval_directory = tmp_path / "eval"
    _write_json(eval_directory / "cases.json", [{"id": "CASE-001"}])
    _write_json(
        runtime / "sql_smoke_report.json",
        [
            {
                "id": "SQL-001",
                "question": "正确 SQL",
                "passed": True,
                "generated_row_count": 2,
                "reference_row_count": 2,
                "errors": [],
                "metrics": {"total_tokens": 100, "total_latency_ms": 1000},
            },
            {
                "id": "SQL-002",
                "question": "错误 SQL",
                "passed": False,
                "generated_row_count": 1,
                "reference_row_count": 2,
                "errors": [],
                "metrics": {"total_tokens": 200, "total_latency_ms": 3000},
            },
        ],
    )
    _write_json(
        runtime / "rag_eval_report.json",
        [
            {
                "id": "RAG-001",
                "question": "正确引用",
                "expect_answer": True,
                "passed": True,
                "expected_document_ids": ["POL-001"],
                "cited_document_ids": ["POL-001"],
                "errors": [],
                "metrics": {"total_tokens": 300, "total_latency_ms": 2000},
            },
            {
                "id": "RAG-002",
                "question": "错误引用",
                "expect_answer": True,
                "passed": False,
                "expected_document_ids": ["POL-002"],
                "cited_document_ids": ["POL-001"],
                "errors": [],
                "metrics": {"total_tokens": 400, "total_latency_ms": 4000},
            },
            {
                "id": "RAG-003",
                "question": "正确拒答",
                "expect_answer": False,
                "passed": True,
                "expected_document_ids": [],
                "cited_document_ids": [],
                "errors": ["RAG_NO_EVIDENCE"],
                "metrics": {"total_tokens": 0, "total_latency_ms": 500},
            },
        ],
    )
    _write_json(
        runtime / "hybrid_live_report.json",
        [
            {
                "id": "HYBRID-001",
                "question": "引用失败",
                "passed": False,
                "sql_passed": True,
                "citation_passed": False,
                "expected_document_ids": ["POL-003"],
                "cited_document_ids": [],
                "errors": [],
                "metrics": {"total_tokens": 500, "total_latency_ms": 5000},
            }
        ],
    )
    _write_json(
        runtime / "comprehensive_eval_report.json",
        {
            "duration_ms": 123.4,
            "summary": {
                "passed": 4,
                "total": 5,
                "pass_rate": 0.8,
                "categories": {"router": {"passed": 4, "total": 5, "pass_rate": 0.8}},
            },
        },
    )
    _write_json(
        runtime / "challenge_eval_report.json",
        [
            {
                "id": "SQL-CH-001",
                "set_type": "challenge",
                "category": "sql_boundary",
                "branch": "sql",
                "question": "边界题",
                "passed": True,
                "expected": {"row_count": 0},
                "actual": {"row_count": 0},
                "errors": [],
                "metrics": {"total_tokens": 50, "total_latency_ms": 700},
            }
        ],
    )
    return build_evaluation_run(
        project_root=tmp_path,
        report_directory=runtime,
        eval_directory=eval_directory,
        label="测试批次",
        model="test-model",
        run_id="run-test-001",
        generated_at=datetime(2026, 7, 24, 8, 0, tzinfo=UTC),
    )


def test_builds_branch_metrics_and_deterministic_failures(tmp_path: Path) -> None:
    run = _build_fixture_run(tmp_path)

    assert run["total_cases"] == 6
    assert run["total_passed"] == 3
    assert run["branches"]["sql"]["accuracy"] == 0.5
    assert run["branches"]["sql"]["p50_latency_ms"] == 2000.0
    assert run["branches"]["sql"]["p95_latency_ms"] == 2900.0
    assert run["branches"]["rag"]["rejected"] == 1
    assert run["branches"]["rag"]["rejection_rate"] == 0.3333
    assert run["quality_gate"]["accuracy"] == 0.8
    assert run["evaluation_sets"]["normal"]["total"] == 6
    assert run["evaluation_sets"]["challenge"]["total"] == 1
    assert run["evaluation_sets"]["challenge"]["categories"]["sql_boundary"]["passed"] == 1
    assert run["evaluation_sets"]["multi_turn"]["total"] == 0
    assert run["evaluation_sets"]["resilience"]["total"] == 0
    assert run["failure_count"] == 3
    assert {failure["failure_type"] for failure in run["failures"]} == {
        "row_count_mismatch",
        "citation_missing",
        "hybrid_citation_failed",
    }


def test_saves_lists_and_refuses_to_overwrite_run(tmp_path: Path) -> None:
    run = _build_fixture_run(tmp_path)
    run_directory = tmp_path / "runs"

    target = save_evaluation_run(run, run_directory)

    assert target.name == "run-test-001.json"
    assert load_evaluation_run(run_directory, "run-test-001") == run
    assert load_evaluation_runs(run_directory)[0]["run_id"] == "run-test-001"
    assert load_evaluation_run(run_directory, "../secret") is None
    with pytest.raises(FileExistsError):
        save_evaluation_run(run, run_directory)

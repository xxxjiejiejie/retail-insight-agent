import json
from pathlib import Path

from app.rag.loader import load_policy_documents
from scripts.evaluate_hybrid_live import DEFAULT_CASE_IDS, REPORT_PATH, report_path_for

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_sql_evaluation_has_30_unique_cases() -> None:
    cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json").read_text(encoding="utf-8")
    )

    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert all(case["reference_sql"].strip() for case in cases)


def test_rag_evaluation_references_known_policy_documents() -> None:
    cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "rag_cases.json").read_text(encoding="utf-8")
    )
    documents = load_policy_documents(PROJECT_ROOT / "data" / "documents")
    known_ids = {document.document_id for document in documents}

    assert len(cases) == 20
    assert len({case["id"] for case in cases}) == 20
    assert sum(not case["expect_answer"] for case in cases) == 3
    assert all(set(case["expected_document_ids"]) <= known_ids for case in cases)


def test_comprehensive_evaluation_defines_100_checks() -> None:
    sql_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json").read_text(
            encoding="utf-8"
        )
    )
    rag_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "rag_cases.json").read_text(encoding="utf-8")
    )
    router_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "router_cases.json").read_text(encoding="utf-8")
    )
    hybrid_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "hybrid_cases.json").read_text(encoding="utf-8")
    )
    safety_payload = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "sql_safety_cases.json").read_text(
            encoding="utf-8"
        )
    )

    all_ids = {
        case["id"]
        for cases in (sql_cases, rag_cases, router_cases, hybrid_cases, safety_payload["cases"])
        for case in cases
    }
    assert len(sql_cases) == 30
    assert len(rag_cases) == 20
    assert len(router_cases) == 25
    assert len(hybrid_cases) == 10
    assert len(safety_payload["cases"]) == 15
    assert len(all_ids) == 100


def test_five_hybrid_cases_have_valid_sql_references() -> None:
    hybrid_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "hybrid_cases.json").read_text(encoding="utf-8")
    )
    sql_cases = json.loads(
        (PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json").read_text(
            encoding="utf-8"
        )
    )
    known_sql_ids = {case["id"] for case in sql_cases}
    reference_backed = [case for case in hybrid_cases if case.get("reference_sql_case_id")]

    assert len(reference_backed) == 5
    assert all(case["reference_sql_case_id"] in known_sql_ids for case in reference_backed)


def test_hybrid_focused_rerun_uses_separate_report() -> None:
    assert report_path_for(DEFAULT_CASE_IDS) == REPORT_PATH
    assert report_path_for({"HYBRID-003"}).name == "hybrid_live_hybrid_003_report.json"

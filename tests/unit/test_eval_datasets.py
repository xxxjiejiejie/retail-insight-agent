import json
from pathlib import Path

from app.rag.loader import load_policy_documents

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

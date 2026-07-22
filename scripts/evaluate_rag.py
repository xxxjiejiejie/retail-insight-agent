"""Evaluate RAG citation recall and no-answer behavior."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.rag.service import handle_rag_question

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "rag_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "rag_eval_report.json"


async def evaluate() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    report: list[dict[str, Any]] = []
    for case in cases:
        result = await handle_rag_question(case["question"])
        cited_document_ids = {
            citation.get("document_id")
            for citation in result.get("citations", [])
            if citation.get("document_id")
        }
        expected_document_ids = set(case["expected_document_ids"])
        if case["expect_answer"]:
            passed = not result.get("errors") and expected_document_ids <= cited_document_ids
        else:
            passed = not result.get("citations") and bool(result.get("errors"))
        entry = {
            "id": case["id"],
            "question": case["question"],
            "expect_answer": case["expect_answer"],
            "passed": passed,
            "expected_document_ids": sorted(expected_document_ids),
            "cited_document_ids": sorted(cited_document_ids),
            "answer": result.get("answer"),
            "errors": result.get("errors", []),
            "metrics": result.get("metrics", {}),
        }
        report.append(entry)
        print(
            f"{case['id']} passed={str(passed).lower()} "
            f"citations={entry['metrics'].get('citation_count', 0)}"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def main() -> None:
    report = await evaluate()
    passed_count = sum(1 for entry in report if entry["passed"])
    print(f"summary={passed_count}/{len(report)} report={REPORT_PATH}")
    if passed_count != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

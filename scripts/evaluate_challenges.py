"""Run SQL boundary, RAG out-of-scope, and prompt-injection challenges."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.evaluation.metrics import result_values_match
from app.graph.nodes import hybrid_node
from app.rag.service import handle_rag_question
from app.sql_agent.executor import execute_read_only_sql
from app.sql_agent.service import handle_sql_question

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "challenge_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "challenge_eval_report.json"
INFRASTRUCTURE_ERRORS = {
    "ConfigurationError",
    "DatabaseQueryError",
    "IntegrationError",
    "LLM_API_KEY_NOT_CONFIGURED",
    "LLMResponseError",
}


def _contains_forbidden(answer: str, forbidden_terms: list[str]) -> list[str]:
    normalized = answer.casefold()
    return [term for term in forbidden_terms if term.casefold() in normalized]


def _has_infrastructure_error(errors: list[str]) -> bool:
    return bool(INFRASTRUCTURE_ERRORS.intersection(errors))


async def _evaluate_sql_boundaries(
    cases: list[dict[str, Any]],
    *,
    engine: Any,
    schema: Any,
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for case in cases:
        result = await handle_sql_question(case["question"], engine=engine)
        generated_result = result.get("sql_result")
        reference = await execute_read_only_sql(case["reference_sql"], schema, engine=engine)
        passed = bool(
            generated_result
            and result_values_match(
                generated_result["rows"],
                reference.rows,
                comparison=case.get("comparison"),
            )
        )
        report.append(
            {
                "id": case["id"],
                "set_type": "challenge",
                "category": "sql_boundary",
                "branch": "sql",
                "question": case["question"],
                "passed": passed,
                "expected": {"row_count": reference.row_count},
                "actual": {
                    "row_count": generated_result.get("row_count") if generated_result else None
                },
                "generated_sql": result.get("generated_sql"),
                "generated_row_count": (
                    generated_result.get("row_count") if generated_result else None
                ),
                "reference_row_count": reference.row_count,
                "answer": result.get("answer"),
                "errors": result.get("errors", []),
                "metrics": result.get("metrics", {}),
            }
        )
    return report


async def _evaluate_rag_out_of_scope(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for case in cases:
        result = await handle_rag_question(case["question"])
        cited_ids = sorted(
            {
                citation.get("document_id")
                for citation in result.get("citations", [])
                if citation.get("document_id")
            }
        )
        passed = not cited_ids and bool(result.get("errors"))
        report.append(
            {
                "id": case["id"],
                "set_type": "challenge",
                "category": "rag_out_of_scope",
                "branch": "rag",
                "question": case["question"],
                "passed": passed,
                "expected": {"refused": True, "document_ids": []},
                "actual": {
                    "refused": bool(result.get("errors")),
                    "document_ids": cited_ids,
                },
                "expect_answer": False,
                "expected_document_ids": [],
                "cited_document_ids": cited_ids,
                "answer": result.get("answer"),
                "errors": result.get("errors", []),
                "metrics": result.get("metrics", {}),
            }
        )
    return report


async def _evaluate_prompt_injection(
    cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for case in cases:
        branch = case["branch"]
        if branch == "sql":
            result = await handle_sql_question(case["question"])
        elif branch == "rag":
            result = await handle_rag_question(case["question"])
        else:
            result = await hybrid_node({"user_query": case["question"]})

        answer = str(result.get("answer") or "")
        errors = [str(error) for error in result.get("errors", [])]
        forbidden_matches = _contains_forbidden(answer, case.get("forbidden_terms", []))
        sql_result = result.get("sql_result")
        sql_safety_held = branch == "rag" or sql_result is None or bool(
            result.get("generated_sql")
        )
        cited_ids = sorted(
            {
                citation.get("document_id")
                for citation in result.get("citations", [])
                if citation.get("document_id")
            }
        )
        expected_ids = set(case.get("expected_document_ids", []))
        citation_held = branch != "hybrid" or expected_ids <= set(cited_ids)
        passed = (
            not forbidden_matches
            and sql_safety_held
            and citation_held
            and not _has_infrastructure_error(errors)
        )
        report.append(
            {
                "id": case["id"],
                "set_type": "challenge",
                "category": "prompt_injection",
                "branch": branch,
                "question": case["question"],
                "passed": passed,
                "expected": {
                    "forbidden_matches": [],
                    "sql_safety_held": True,
                    "document_ids": sorted(expected_ids),
                },
                "actual": {
                    "forbidden_matches": forbidden_matches,
                    "sql_safety_held": sql_safety_held,
                    "document_ids": cited_ids,
                },
                "expected_document_ids": sorted(expected_ids),
                "cited_document_ids": cited_ids,
                "generated_sql": result.get("generated_sql"),
                "answer": answer,
                "errors": errors,
                "metrics": result.get("metrics", {}),
            }
        )
    return report


async def evaluate() -> list[dict[str, Any]]:
    payload: dict[str, list[dict[str, Any]]] = json.loads(
        CASES_PATH.read_text(encoding="utf-8")
    )
    engine = get_business_engine()
    try:
        schema = await load_schema_catalog(engine)
        report = await _evaluate_sql_boundaries(
            payload["sql_boundary"], engine=engine, schema=schema
        )
    finally:
        await engine.dispose()

    report.extend(await _evaluate_rag_out_of_scope(payload["rag_out_of_scope"]))
    report.extend(await _evaluate_prompt_injection(payload["prompt_injection"]))
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


async def main() -> None:
    report = await evaluate()
    passed = sum(bool(entry["passed"]) for entry in report)
    for entry in report:
        print(
            f"{entry['id']} category={entry['category']} "
            f"passed={str(entry['passed']).lower()}"
        )
    print(f"summary={passed}/{len(report)} report={REPORT_PATH}")
    if passed != len(report):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

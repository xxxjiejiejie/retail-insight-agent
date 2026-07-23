"""Evaluate local retrieval and reranking without calling the paid LLM API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.rag.hybrid_retriever import HybridPolicyRetriever
from app.rag.lexical import BM25PolicyRetriever
from app.rag.reranker import BGEReranker
from app.rag.vector_store import ChromaPolicyRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "rag_cases.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "rag_retrieval_report.json"


async def main() -> None:
    settings = get_settings()
    cases: list[dict[str, Any]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    retriever = ChromaPolicyRetriever.from_settings()
    lexical_retriever = BM25PolicyRetriever.from_corpus(Path(settings.lexical_corpus_path))
    hybrid_retriever = HybridPolicyRetriever(
        retriever,
        lexical_retriever,
        vector_top_k=settings.rag_vector_top_k,
        lexical_top_k=settings.rag_bm25_top_k,
        rrf_k=settings.rag_rrf_k,
    )
    reranker = BGEReranker.from_settings()
    report: list[dict[str, Any]] = []

    for case in cases:
        vector_candidates = await retriever.retrieve(
            case["question"],
            top_k=settings.rag_retrieval_top_k,
        )
        candidates = await hybrid_retriever.retrieve(
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
        vector_ids = {item.chunk.document_id for item in vector_candidates}
        hybrid_ids = {item.chunk.document_id for item in candidates}
        vector_hit = expected_ids <= vector_ids if expected_ids else True
        hybrid_hit = expected_ids <= hybrid_ids if expected_ids else True
        passed = (
            expected_ids <= actual_ids if case["expect_answer"] else not evidence
        )
        entry = {
            "id": case["id"],
            "passed": passed,
            "expect_answer": case["expect_answer"],
            "expected_document_ids": sorted(expected_ids),
            "vector_recall_hit": vector_hit,
            "hybrid_recall_hit": hybrid_hit,
            "evidence_document_ids": sorted(actual_ids),
            "top_scores": [round(item.score, 6) for item in ranked],
        }
        report.append(entry)
        print(
            f"{case['id']} passed={str(passed).lower()} "
            f"vector_hit={str(vector_hit).lower()} hybrid_hit={str(hybrid_hit).lower()} "
            f"scores={entry['top_scores']} ids={entry['evidence_document_ids']}"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed_count = sum(1 for entry in report if entry["passed"])
    answer_cases = [entry for entry in report if entry["expect_answer"]]
    vector_hits = sum(1 for entry in answer_cases if entry["vector_recall_hit"])
    hybrid_hits = sum(1 for entry in answer_cases if entry["hybrid_recall_hit"])
    print(
        f"summary={passed_count}/{len(report)} "
        f"vector_recall={vector_hits}/{len(answer_cases)} "
        f"hybrid_recall={hybrid_hits}/{len(answer_cases)} report={REPORT_PATH}"
    )


if __name__ == "__main__":
    asyncio.run(main())

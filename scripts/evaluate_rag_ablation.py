"""Evaluate four local retrieval pipelines against chunk-level ground truth."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections import defaultdict
from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.evaluation.rag_ablation import ranking_metrics
from app.rag.lexical import BM25PolicyRetriever
from app.rag.models import DocumentChunk, RetrievedChunk
from app.rag.reranker import BGEReranker
from app.rag.vector_store import ChromaPolicyRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_PATH = PROJECT_ROOT / "data" / "eval" / "rag_ground_truth.json"
CORPUS_REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "policy_corpus_report.json"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "rag_ablation_report.json"
PIPELINE_LABELS = {
    "vector": "Vector",
    "bm25": "BM25",
    "rrf": "RRF",
    "rrf_reranker": "RRF + BGE Reranker",
}
TOP_K = 5


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


async def _timed_retrieve(
    operation: Awaitable[list[RetrievedChunk]],
) -> tuple[list[RetrievedChunk], float]:
    started = time.perf_counter()
    results = await operation
    return results, (time.perf_counter() - started) * 1000


def _rrf(
    vector_results: list[RetrievedChunk],
    bm25_results: list[RetrievedChunk],
    *,
    rrf_k: int,
    top_k: int,
) -> list[RetrievedChunk]:
    scores: defaultdict[str, float] = defaultdict(float)
    chunks: dict[str, DocumentChunk] = {}
    for results in (vector_results, bm25_results):
        for rank, result in enumerate(results, 1):
            chunk_id = result.chunk.chunk_id
            chunks[chunk_id] = result.chunk
            scores[chunk_id] += 1.0 / (rrf_k + rank)
    ranked_ids = sorted(scores, key=scores.__getitem__, reverse=True)
    return [
        RetrievedChunk(chunk=chunks[chunk_id], score=scores[chunk_id])
        for chunk_id in ranked_ids[:top_k]
    ]


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _pipeline_summary(
    pipeline: str,
    case_results: list[dict[str, Any]],
) -> dict[str, Any]:
    answerable = [entry for entry in case_results if entry["expect_answer"]]
    negatives = [entry for entry in case_results if not entry["expect_answer"]]
    summary = {
        "label": PIPELINE_LABELS[pipeline],
        "hit_at_5": round(_mean([entry["metrics"]["hit_at_5"] for entry in answerable]), 4),
        "mrr_at_5": round(_mean([entry["metrics"]["mrr_at_5"] for entry in answerable]), 4),
        "ndcg_at_5": round(_mean([entry["metrics"]["ndcg_at_5"] for entry in answerable]), 4),
        "p50_latency_ms": round(
            _percentile([entry["latency_ms"] for entry in case_results], 0.5), 2
        ),
        "p95_latency_ms": round(
            _percentile([entry["latency_ms"] for entry in case_results], 0.95), 2
        ),
        "evaluated_answerable_cases": len(answerable),
        "failure_count": sum(entry["metrics"]["hit_at_5"] == 0 for entry in answerable),
        "negative_nonempty_rate": round(
            _mean([float(bool(entry["ranked_chunk_ids"])) for entry in negatives]), 4
        ),
        "negative_mean_top_score": round(
            _mean([entry["top_score"] for entry in negatives]), 6
        ),
    }
    return summary


def _validate_ground_truth(
    payload: dict[str, Any],
    corpus_chunk_ids: set[str],
) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Ground Truth cases 必须是非空数组")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Ground Truth case 必须是对象")
        case_id = str(case.get("id") or "")
        if not case_id or case_id in case_ids:
            raise ValueError(f"Ground Truth case id 缺失或重复：{case_id}")
        case_ids.add(case_id)
        relevant = case.get("relevant_chunks")
        if not isinstance(relevant, list):
            raise ValueError(f"{case_id} 缺少 relevant_chunks")
        unknown = {
            str(item.get("chunk_id"))
            for item in relevant
            if isinstance(item, dict) and str(item.get("chunk_id")) not in corpus_chunk_ids
        }
        if unknown:
            raise ValueError(f"{case_id} 引用了不存在的 chunk：{sorted(unknown)}")
    return cases


async def evaluate() -> dict[str, Any]:
    settings = get_settings()
    ground_truth = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))
    corpus_report = json.loads(CORPUS_REPORT_PATH.read_text(encoding="utf-8"))
    lexical_corpus_path = Path(settings.lexical_corpus_path)
    lexical_payload = json.loads(lexical_corpus_path.read_text(encoding="utf-8"))
    corpus_chunk_ids = {
        str(chunk["chunk_id"])
        for chunk in lexical_payload["chunks"]
        if isinstance(chunk, dict) and chunk.get("chunk_id")
    }
    cases = _validate_ground_truth(ground_truth, corpus_chunk_ids)
    lexical = BM25PolicyRetriever.from_corpus(lexical_corpus_path)
    vector = ChromaPolicyRetriever.from_settings()
    reranker = BGEReranker.from_settings()
    results_by_pipeline: dict[str, list[dict[str, Any]]] = {
        pipeline: [] for pipeline in PIPELINE_LABELS
    }

    for position, case in enumerate(cases, 1):
        query = str(case["question"])
        retrieval_started = time.perf_counter()
        (vector_results, vector_latency), (bm25_results, bm25_latency) = await asyncio.gather(
            _timed_retrieve(
                vector.retrieve(query, top_k=settings.rag_vector_top_k)
            ),
            _timed_retrieve(
                lexical.retrieve(query, top_k=settings.rag_bm25_top_k)
            ),
        )
        parallel_retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        fusion_started = time.perf_counter()
        fused_candidates = _rrf(
            vector_results,
            bm25_results,
            rrf_k=settings.rag_rrf_k,
            top_k=max(settings.rag_retrieval_top_k, TOP_K),
        )
        fusion_ms = (time.perf_counter() - fusion_started) * 1000
        rerank_started = time.perf_counter()
        reranked = await reranker.rerank(query, fused_candidates, top_k=TOP_K)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
        rankings = {
            "vector": (vector_results[:TOP_K], vector_latency),
            "bm25": (bm25_results[:TOP_K], bm25_latency),
            "rrf": (fused_candidates[:TOP_K], parallel_retrieval_ms + fusion_ms),
            "rrf_reranker": (
                reranked,
                parallel_retrieval_ms + fusion_ms + rerank_ms,
            ),
        }
        relevance = {
            str(item["chunk_id"]): int(item["relevance"])
            for item in case["relevant_chunks"]
        }
        for pipeline, (ranked, latency_ms) in rankings.items():
            ranked_ids = [item.chunk.chunk_id for item in ranked]
            results_by_pipeline[pipeline].append(
                {
                    "case_id": case["id"],
                    "split": case["split"],
                    "category": case["category"],
                    "question": query,
                    "expect_answer": bool(case["expect_answer"]),
                    "expected_document_ids": case["expected_document_ids"],
                    "ranked_chunk_ids": ranked_ids,
                    "ranked_document_ids": [item.chunk.document_id for item in ranked],
                    "top_score": round(float(ranked[0].score), 6) if ranked else 0.0,
                    "metrics": ranking_metrics(ranked_ids, relevance, k=TOP_K),
                    "latency_ms": round(latency_ms, 2),
                }
            )
        print(f"[{position:02d}/{len(cases)}] {case['id']} complete")

    pipeline_summaries = {
        pipeline: _pipeline_summary(pipeline, entries)
        for pipeline, entries in results_by_pipeline.items()
    }
    failures = [
        {
            "pipeline": pipeline,
            "case_id": entry["case_id"],
            "split": entry["split"],
            "category": entry["category"],
            "question": entry["question"],
            "expected_document_ids": entry["expected_document_ids"],
            "retrieved_document_ids": entry["ranked_document_ids"],
            "retrieved_chunk_ids": entry["ranked_chunk_ids"],
        }
        for pipeline, entries in results_by_pipeline.items()
        for entry in entries
        if entry["expect_answer"] and entry["metrics"]["hit_at_5"] == 0
    ]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_version": ground_truth["dataset_version"],
        "top_k": TOP_K,
        "total_cases": len(cases),
        "answerable_cases": sum(bool(case["expect_answer"]) for case in cases),
        "negative_cases": sum(not bool(case["expect_answer"]) for case in cases),
        "corpus": {
            "document_count": corpus_report["document_count"],
            "chunk_count": corpus_report["chunk_count"],
            "domain_count": corpus_report["domain_count"],
            "corpus_version": corpus_report["corpus_version"],
        },
        "pipelines": pipeline_summaries,
        "negative_summary": {
            "case_count": sum(not bool(case["expect_answer"]) for case in cases),
            "note": (
                "库外题不计入 Hit/MRR/nDCG。裸检索器返回候选不等于系统作答，"
                "本项仅记录候选非空率和首位分数，拒答能力由端到端 RAG 评测衡量。"
            ),
        },
        "failures": failures,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def main() -> None:
    report = await evaluate()
    for pipeline, metrics in report["pipelines"].items():
        print(
            f"{pipeline}: Hit@5={metrics['hit_at_5']:.4f} "
            f"MRR@5={metrics['mrr_at_5']:.4f} nDCG@5={metrics['ndcg_at_5']:.4f}"
        )
    print(f"failures={len(report['failures'])} report={REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

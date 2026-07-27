from __future__ import annotations

import re
from dataclasses import asdict
from time import perf_counter
from typing import Any

from app.core.config import get_settings
from app.core.errors import ConfigurationError, IntegrationError, RetailInsightError
from app.llm.deepseek import TextGenerator, get_llm_client
from app.observability.langsmith import observe_chain
from app.rag.interfaces import PolicyReranker, PolicyRetriever
from app.rag.models import RetrievedChunk
from app.rag.prompts import RAG_SYSTEM_PROMPT, build_rag_user_prompt
from app.rag.runtime import get_policy_reranker, get_policy_retriever

ABSTENTION_PHRASES = (
    "无法从现有制度确认",
    "无法根据现有制度确认",
    "现有制度无法确认",
    "现有制度证据不足",
    "无法可靠回答",
)


def _citation_payload(result: RetrievedChunk) -> dict[str, Any]:
    chunk = result.chunk
    return {
        "source": chunk.title,
        "section": chunk.section,
        "page": chunk.page,
        "excerpt": chunk.content[:300],
        "document_id": chunk.document_id,
        "version": chunk.version,
        "paragraph_id": chunk.paragraph_id,
        "chunk_id": chunk.chunk_id,
        "relevance_score": round(result.score, 6),
    }


def _retrieved_payload(result: RetrievedChunk) -> dict[str, Any]:
    return {**asdict(result.chunk), "score": round(result.score, 6)}


def _extract_citation_indices(answer: str, *, context_count: int) -> list[int]:
    indices: list[int] = []
    for raw_index in re.findall(r"\[(\d+)]", answer):
        index = int(raw_index)
        if 1 <= index <= context_count and index not in indices:
            indices.append(index)
    return indices


def _answer_abstains(answer: str) -> bool:
    normalized = "".join(answer.split())
    return any(phrase in normalized for phrase in ABSTENTION_PHRASES)


def _failure_result(
    answer: str,
    *,
    error_code: str,
    started: float,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "retrieved_docs": [],
        "citations": [],
        "answer": answer,
        "errors": [error_code],
        "metrics": {
            **(metrics or {}),
            "total_latency_ms": round((perf_counter() - started) * 1000, 2),
        },
    }


async def handle_rag_question(
    query: str,
    *,
    retriever: PolicyRetriever | None = None,
    reranker: PolicyReranker | None = None,
    llm_client: TextGenerator | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    try:
        active_retriever = retriever or get_policy_retriever()
        active_reranker = reranker or get_policy_reranker()
        active_llm = llm_client or get_llm_client()
    except RetailInsightError as exc:
        return _failure_result(
            f"制度知识库尚未就绪：{exc}",
            error_code=type(exc).__name__,
            started=started,
        )

    retrieval_started = perf_counter()
    try:
        async with observe_chain(
            "rag.retrieve",
            inputs={"query": query, "top_k": settings.rag_retrieval_top_k},
            tags=["rag", "retriever"],
        ) as retrieval_span:
            candidates = await active_retriever.retrieve(
                query,
                top_k=settings.rag_retrieval_top_k,
            )
            await retrieval_span.end(
                {
                    "retrieved_count": len(candidates),
                    "documents": [
                        {
                            "chunk_id": item.chunk.chunk_id,
                            "document_id": item.chunk.document_id,
                            "title": item.chunk.title,
                            "section": item.chunk.section,
                            "score": round(item.score, 6),
                        }
                        for item in candidates
                    ],
                }
            )
    except RetailInsightError as exc:
        return _failure_result(
            f"制度检索暂时不可用：{exc}",
            error_code=type(exc).__name__,
            started=started,
        )
    retrieval_ms = round((perf_counter() - retrieval_started) * 1000, 2)

    if not candidates:
        return _failure_result(
            "现有制度库中没有找到足够依据，请补充制度名称或更具体的问题。",
            error_code="RAG_NO_EVIDENCE",
            started=started,
            metrics={"retrieval_ms": retrieval_ms, "retrieved_count": 0},
        )

    rerank_started = perf_counter()
    try:
        async with observe_chain(
            "rag.rerank",
            inputs={
                "query": query,
                "candidate_count": len(candidates),
                "top_k": settings.rag_rerank_top_k,
            },
            tags=["rag", "reranker"],
        ) as rerank_span:
            ranked = await active_reranker.rerank(
                query,
                candidates,
                top_k=settings.rag_rerank_top_k,
            )
            await rerank_span.end(
                {
                    "reranked_count": len(ranked),
                    "documents": [
                        {
                            "chunk_id": item.chunk.chunk_id,
                            "document_id": item.chunk.document_id,
                            "score": round(item.score, 6),
                        }
                        for item in ranked
                    ],
                }
            )
    except RetailInsightError as exc:
        return _failure_result(
            f"制度证据重排暂时不可用：{exc}",
            error_code=type(exc).__name__,
            started=started,
            metrics={"retrieval_ms": retrieval_ms},
        )
    rerank_ms = round((perf_counter() - rerank_started) * 1000, 2)

    evidence = [
        result for result in ranked if result.score >= settings.rag_min_relevance_score
    ]
    if not evidence:
        return _failure_result(
            "现有制度证据与问题的相关度不足，无法可靠回答。请补充制度名称或业务场景。",
            error_code="RAG_LOW_RELEVANCE",
            started=started,
            metrics={
                "retrieval_ms": retrieval_ms,
                "rerank_ms": rerank_ms,
                "retrieved_count": len(candidates),
                "reranked_count": len(ranked),
            },
        )

    contexts = [result.to_context(index) for index, result in enumerate(evidence, 1)]
    try:
        llm_result = await active_llm.generate_text(
            system=RAG_SYSTEM_PROMPT,
            user=build_rag_user_prompt(query, contexts),
            max_tokens=1_000,
        )
    except (ConfigurationError, IntegrationError) as exc:
        return _failure_result(
            f"已找到制度依据，但答案生成暂时不可用：{exc}",
            error_code=type(exc).__name__,
            started=started,
            metrics={
                "retrieval_ms": retrieval_ms,
                "rerank_ms": rerank_ms,
                "retrieved_count": len(candidates),
                "reranked_count": len(ranked),
            },
        )

    if _answer_abstains(llm_result.content):
        return _failure_result(
            "现有制度证据不足，无法可靠回答。请补充相关制度文件或业务范围。",
            error_code="RAG_ANSWER_ABSTAINED",
            started=started,
            metrics={
                "retrieval_ms": retrieval_ms,
                "rerank_ms": rerank_ms,
                "retrieved_count": len(candidates),
                "reranked_count": len(ranked),
                "prompt_tokens": llm_result.prompt_tokens,
                "completion_tokens": llm_result.completion_tokens,
                "total_tokens": llm_result.total_tokens,
                "llm_latency_ms": llm_result.latency_ms,
            },
        )

    cited_indices = _extract_citation_indices(
        llm_result.content,
        context_count=len(evidence),
    )
    citations = [_citation_payload(evidence[index - 1]) for index in cited_indices]
    citation_errors = [] if citations else ["RAG_CITATION_MISSING"]
    return {
        "retrieved_docs": [_retrieved_payload(result) for result in evidence],
        "citations": citations,
        "answer": llm_result.content,
        "errors": citation_errors,
        "metrics": {
            "retrieval_ms": retrieval_ms,
            "rerank_ms": rerank_ms,
            "retrieved_count": len(candidates),
            "reranked_count": len(ranked),
            "evidence_count": len(evidence),
            "citation_count": len(citations),
            "prompt_tokens": llm_result.prompt_tokens,
            "completion_tokens": llm_result.completion_tokens,
            "total_tokens": llm_result.total_tokens,
            "llm_latency_ms": llm_result.latency_ms,
            "total_latency_ms": round((perf_counter() - started) * 1000, 2),
        },
    }

from __future__ import annotations

import pytest

from app.llm.deepseek import LLMTextResponse
from app.rag.models import DocumentChunk, RetrievedChunk
from app.rag.service import handle_rag_question


def make_result(score: float = 0.92) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(
            chunk_id="chunk-1",
            document_id="POL-PROMO-001",
            title="门店促销与折扣审批制度",
            version="1.0",
            effective_date="2026-01-01",
            source="promotion_approval_policy.md",
            section="折扣审批层级",
            paragraph_id="POL-PROMO-001-S02-P01",
            content="折扣低于八折的活动必须由运营总监审批。",
        ),
        score=score,
    )


def make_other_result(score: float = 0.8) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=DocumentChunk(
            chunk_id="chunk-2",
            document_id="POL-RETURN-001",
            title="门店退换货管理制度",
            version="1.0",
            effective_date="2026-01-01",
            source="return_exchange_policy.md",
            section="受理条件",
            paragraph_id="POL-RETURN-001-S02-P01",
            content="普通商品无质量问题可在七日内申请退货。",
        ),
        score=score,
    )


class FakeRetriever:
    def __init__(self, results: list[RetrievedChunk]):
        self.results = results
        self.requested_top_k = 0

    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        self.requested_top_k = top_k
        return self.results


class FakeReranker:
    def __init__(self, results: list[RetrievedChunk]):
        self.results = results
        self.requested_top_k = 0

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        top_k: int,
    ) -> list[RetrievedChunk]:
        self.requested_top_k = top_k
        return self.results


class FakeAnswerGenerator:
    def __init__(self):
        self.prompt = ""

    async def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1_200,
    ) -> LLMTextResponse:
        self.prompt = user
        return LLMTextResponse(
            content="低于八折的促销须由运营总监审批。[1]",
            prompt_tokens=80,
            completion_tokens=20,
            latency_ms=15.5,
            model="test-model",
        )


@pytest.mark.asyncio
async def test_returns_grounded_answer_citations_and_metrics() -> None:
    result_chunk = make_result()
    retriever = FakeRetriever([result_chunk])
    reranker = FakeReranker([result_chunk])
    llm = FakeAnswerGenerator()

    result = await handle_rag_question(
        "折扣低于八折由谁审批？",
        retriever=retriever,
        reranker=reranker,
        llm_client=llm,
    )

    assert result["answer"].endswith("[1]")
    assert result["citations"][0]["document_id"] == "POL-PROMO-001"
    assert result["citations"][0]["paragraph_id"] == "POL-PROMO-001-S02-P01"
    assert result["metrics"]["total_tokens"] == 100
    assert result["metrics"]["citation_count"] == 1
    assert retriever.requested_top_k == 12
    assert reranker.requested_top_k == 5
    assert "不得" not in llm.prompt
    assert "折扣低于八折" in llm.prompt


@pytest.mark.asyncio
async def test_returns_only_citations_used_by_the_answer() -> None:
    cited = make_result()
    uncited = make_other_result()
    result = await handle_rag_question(
        "折扣低于八折由谁审批？",
        retriever=FakeRetriever([cited, uncited]),
        reranker=FakeReranker([cited, uncited]),
        llm_client=FakeAnswerGenerator(),
    )

    assert [item["document_id"] for item in result["citations"]] == ["POL-PROMO-001"]
    assert result["metrics"]["evidence_count"] == 2


@pytest.mark.asyncio
async def test_refuses_when_retrieval_returns_no_evidence() -> None:
    result = await handle_rag_question(
        "公司是否提供住房补贴？",
        retriever=FakeRetriever([]),
        reranker=FakeReranker([]),
        llm_client=FakeAnswerGenerator(),
    )

    assert result["citations"] == []
    assert result["errors"] == ["RAG_NO_EVIDENCE"]
    assert "没有找到足够依据" in result["answer"]


@pytest.mark.asyncio
async def test_refuses_when_reranker_score_is_too_low() -> None:
    low_score = make_result(score=0.05)
    result = await handle_rag_question(
        "公司是否提供住房补贴？",
        retriever=FakeRetriever([low_score]),
        reranker=FakeReranker([low_score]),
        llm_client=FakeAnswerGenerator(),
    )

    assert result["errors"] == ["RAG_LOW_RELEVANCE"]
    assert "相关度不足" in result["answer"]

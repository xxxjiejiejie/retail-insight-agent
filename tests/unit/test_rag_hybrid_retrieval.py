from __future__ import annotations

import pytest

from app.rag.hybrid_retriever import HybridPolicyRetriever
from app.rag.lexical import BM25PolicyRetriever, tokenize_for_bm25
from app.rag.models import DocumentChunk, RetrievedChunk


def make_chunk(chunk_id: str, content: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=f"POL-{chunk_id}",
        title=f"制度 {chunk_id}",
        version="1.0",
        effective_date="2026-07-01",
        source=f"{chunk_id}.md",
        section="规则",
        paragraph_id=f"POL-{chunk_id}-S01-P01",
        content=content,
    )


class FakeRetriever:
    def __init__(self, chunks: list[DocumentChunk]):
        self.chunks = chunks
        self.requested_top_k = 0

    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        self.requested_top_k = top_k
        return [RetrievedChunk(chunk=chunk, score=1.0) for chunk in self.chunks[:top_k]]


def test_chinese_tokenizer_keeps_characters_and_bigrams() -> None:
    tokens = tokenize_for_bm25("促销预算 2026")

    assert "促" in tokens
    assert "促销" in tokens
    assert "2026" in tokens


@pytest.mark.asyncio
async def test_bm25_prioritizes_exact_policy_terms() -> None:
    expected = make_chunk("PROMO", "折扣低于八折且预算超过两万元，必须由运营总监审批。")
    unrelated = make_chunk("RETURN", "普通商品无质量问题可在七日内申请退货。")
    retriever = BM25PolicyRetriever([unrelated, expected])

    results = await retriever.retrieve("预算超过两万元由谁审批", top_k=2)

    assert results[0].chunk.chunk_id == "PROMO"
    assert results[0].score > 0


@pytest.mark.asyncio
async def test_hybrid_retriever_fuses_and_deduplicates_rankings() -> None:
    shared = make_chunk("SHARED", "共同证据")
    vector_only = make_chunk("VECTOR", "语义证据")
    lexical_only = make_chunk("LEXICAL", "关键词证据")
    vector = FakeRetriever([shared, vector_only])
    lexical = FakeRetriever([lexical_only, shared])
    retriever = HybridPolicyRetriever(
        vector,
        lexical,
        vector_top_k=2,
        lexical_top_k=2,
        rrf_k=60,
    )

    results = await retriever.retrieve("测试", top_k=3)

    assert results[0].chunk.chunk_id == "SHARED"
    assert len({item.chunk.chunk_id for item in results}) == 3
    assert vector.requested_top_k == 2
    assert lexical.requested_top_k == 2

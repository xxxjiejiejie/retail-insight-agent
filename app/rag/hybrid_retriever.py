from __future__ import annotations

import asyncio
from collections import defaultdict

from app.rag.interfaces import PolicyRetriever
from app.rag.models import DocumentChunk, RetrievedChunk


class HybridPolicyRetriever:
    def __init__(
        self,
        vector_retriever: PolicyRetriever,
        lexical_retriever: PolicyRetriever,
        *,
        vector_top_k: int = 20,
        lexical_top_k: int = 20,
        rrf_k: int = 60,
    ):
        if min(vector_top_k, lexical_top_k, rrf_k) <= 0:
            raise ValueError("混合召回参数必须大于 0")
        self._vector_retriever = vector_retriever
        self._lexical_retriever = lexical_retriever
        self._vector_top_k = vector_top_k
        self._lexical_top_k = lexical_top_k
        self._rrf_k = rrf_k

    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        vector_results, lexical_results = await asyncio.gather(
            self._vector_retriever.retrieve(query, top_k=self._vector_top_k),
            self._lexical_retriever.retrieve(query, top_k=self._lexical_top_k),
        )
        scores: defaultdict[str, float] = defaultdict(float)
        chunks: dict[str, DocumentChunk] = {}
        for results in (vector_results, lexical_results):
            for rank, result in enumerate(results, 1):
                chunk_id = result.chunk.chunk_id
                chunks[chunk_id] = result.chunk
                scores[chunk_id] += 1.0 / (self._rrf_k + rank)
        ranked_ids = sorted(scores, key=scores.__getitem__, reverse=True)
        return [
            RetrievedChunk(chunk=chunks[chunk_id], score=scores[chunk_id])
            for chunk_id in ranked_ids[:top_k]
        ]

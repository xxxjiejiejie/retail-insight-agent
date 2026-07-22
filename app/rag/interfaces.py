from __future__ import annotations

from typing import Protocol

from app.rag.models import RetrievedChunk


class PolicyRetriever(Protocol):
    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]: ...


class PolicyReranker(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        top_k: int,
    ) -> list[RetrievedChunk]: ...

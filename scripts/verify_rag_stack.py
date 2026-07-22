"""Verify local Chroma retrieval, BGE reranking, and CUDA availability."""

from __future__ import annotations

import asyncio

import torch

from app.rag.reranker import BGEReranker
from app.rag.vector_store import ChromaPolicyRetriever


async def main() -> None:
    query = "会员积分过期后能否恢复？"
    retriever = ChromaPolicyRetriever.from_settings()
    candidates = await retriever.retrieve(query, top_k=12)
    reranker = BGEReranker.from_settings()
    reranked = await reranker.rerank(query, candidates, top_k=5)

    print(f"cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"gpu={torch.cuda.get_device_name(0)}")
    print(f"retrieved={len(candidates)} reranked={len(reranked)}")
    for rank, item in enumerate(reranked, start=1):
        print(
            f"rank={rank} document_id={item.chunk.document_id} "
            f"section={item.chunk.section} score={item.score:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())

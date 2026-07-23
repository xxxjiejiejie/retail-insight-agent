"""Verify local Chroma retrieval, BGE reranking, and CUDA availability."""

from __future__ import annotations

import argparse
import asyncio
import importlib
from typing import Any

from app.rag.reranker import BGEReranker
from app.rag.runtime import get_policy_retriever


async def main(query: str) -> None:
    torch: Any = importlib.import_module("torch")
    retriever = get_policy_retriever()
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
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="会员积分过期后能否恢复？")
    args = parser.parse_args()
    asyncio.run(main(args.query))

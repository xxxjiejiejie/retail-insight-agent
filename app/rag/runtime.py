from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import ConfigurationError
from app.rag.interfaces import PolicyReranker, PolicyRetriever


@lru_cache
def get_policy_retriever() -> PolicyRetriever:
    try:
        from app.rag.hybrid_retriever import HybridPolicyRetriever
        from app.rag.lexical import BM25PolicyRetriever
        from app.rag.vector_store import ChromaPolicyRetriever
    except ImportError as exc:
        raise ConfigurationError(
            "RAG 本地依赖尚未安装，请先完成经确认的模型与 Chroma 安装"
        ) from exc
    settings = get_settings()
    vector_retriever = ChromaPolicyRetriever.from_settings()
    lexical_retriever = BM25PolicyRetriever.from_corpus(Path(settings.lexical_corpus_path))
    return HybridPolicyRetriever(
        vector_retriever,
        lexical_retriever,
        vector_top_k=settings.rag_vector_top_k,
        lexical_top_k=settings.rag_bm25_top_k,
        rrf_k=settings.rag_rrf_k,
    )


@lru_cache
def get_policy_reranker() -> PolicyReranker:
    try:
        from app.rag.reranker import BGEReranker
    except ImportError as exc:
        raise ConfigurationError("RAG 本地依赖尚未安装，请先完成经确认的 Reranker 安装") from exc
    return BGEReranker.from_settings()

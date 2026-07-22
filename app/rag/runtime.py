from __future__ import annotations

from functools import lru_cache

from app.core.errors import ConfigurationError
from app.rag.interfaces import PolicyReranker, PolicyRetriever


@lru_cache
def get_policy_retriever() -> PolicyRetriever:
    try:
        from app.rag.vector_store import ChromaPolicyRetriever
    except ImportError as exc:
        raise ConfigurationError(
            "RAG 本地依赖尚未安装，请先完成经确认的模型与 Chroma 安装"
        ) from exc
    return ChromaPolicyRetriever.from_settings()


@lru_cache
def get_policy_reranker() -> PolicyReranker:
    try:
        from app.rag.reranker import BGEReranker
    except ImportError as exc:
        raise ConfigurationError("RAG 本地依赖尚未安装，请先完成经确认的 Reranker 安装") from exc
    return BGEReranker.from_settings()

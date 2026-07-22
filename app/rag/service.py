from typing import Any


async def handle_rag_question(query: str) -> dict[str, Any]:
    """RAG branch contract. Real indexing and retrieval arrive in phase 3."""

    return {
        "retrieved_docs": [],
        "citations": [],
        "answer": (
            "已路由到制度知识问答分支，但制度文档、向量索引和 Reranker 尚未配置。"
            f"当前收到的问题是：{query}"
        ),
    }


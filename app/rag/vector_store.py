from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, IntegrationError
from app.rag.models import DocumentChunk, RetrievedChunk

COLLECTION_NAME = "retail_policy_chunks_v1"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


class ChromaPolicyRetriever:
    def __init__(self, settings: Settings):
        try:
            import chromadb  # type: ignore[import-not-found]
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigurationError("缺少 chromadb 或 sentence-transformers 依赖") from exc

        cache_folder = settings.model_cache_path or None
        self._encoder: Any = SentenceTransformer(
            settings.embedding_model,
            cache_folder=cache_folder,
            local_files_only=settings.model_local_files_only,
        )
        vector_path = Path(settings.vector_store_path)
        vector_path.mkdir(parents=True, exist_ok=True)
        self._client: Any = chromadb.PersistentClient(path=str(vector_path))
        self._collection: Any = self._client.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @classmethod
    def from_settings(cls) -> ChromaPolicyRetriever:
        return cls(get_settings())

    def _encode_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._encoder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def _encode_query(self, query: str) -> list[float]:
        vector = self._encoder.encode(
            f"{QUERY_INSTRUCTION}{query}",
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return cast(list[float], vector.tolist())

    async def replace_index(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            raise ValueError("制度分块不能为空")

        def rebuild() -> int:
            try:
                self._client.delete_collection(COLLECTION_NAME)
            except ValueError:
                pass
            self._collection = self._client.get_or_create_collection(
                COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            batch_size = 64
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                texts = [chunk.content for chunk in batch]
                metadatas = [
                    {
                        key: str(value)
                        for key, value in asdict(chunk).items()
                        if key != "content" and value is not None
                    }
                    for chunk in batch
                ]
                self._collection.upsert(
                    ids=[chunk.chunk_id for chunk in batch],
                    documents=texts,
                    metadatas=metadatas,
                    embeddings=self._encode_documents(texts),
                )
            return len(chunks)

        try:
            return await asyncio.to_thread(rebuild)
        except (OSError, RuntimeError, ValueError) as exc:
            raise IntegrationError("制度向量索引构建失败") from exc

    async def upsert_chunks(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0

        def upsert() -> int:
            batch_size = 64
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                texts = [chunk.content for chunk in batch]
                metadatas = [
                    {
                        key: str(value)
                        for key, value in asdict(chunk).items()
                        if key != "content" and value is not None
                    }
                    for chunk in batch
                ]
                self._collection.upsert(
                    ids=[chunk.chunk_id for chunk in batch],
                    documents=texts,
                    metadatas=metadatas,
                    embeddings=self._encode_documents(texts),
                )
            return len(chunks)

        try:
            return await asyncio.to_thread(upsert)
        except (OSError, RuntimeError, ValueError) as exc:
            raise IntegrationError("制度向量索引增量更新失败") from exc

    async def delete_chunks(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0

        def delete() -> int:
            self._collection.delete(ids=chunk_ids)
            return len(chunk_ids)

        try:
            return await asyncio.to_thread(delete)
        except (OSError, RuntimeError, ValueError) as exc:
            raise IntegrationError("制度向量索引增量删除失败") from exc

    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        def query_index() -> list[RetrievedChunk]:
            if self._collection.count() == 0:
                raise ConfigurationError("制度向量索引为空，请先运行索引脚本")
            raw = self._collection.query(
                query_embeddings=[self._encode_query(query)],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            documents = raw.get("documents", [[]])[0]
            metadatas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]
            results: list[RetrievedChunk] = []
            for content, metadata, distance in zip(
                documents,
                metadatas,
                distances,
                strict=True,
            ):
                if not isinstance(metadata, dict) or not isinstance(content, str):
                    continue
                chunk = DocumentChunk(
                    chunk_id=str(metadata["chunk_id"]),
                    document_id=str(metadata["document_id"]),
                    title=str(metadata["title"]),
                    version=str(metadata["version"]),
                    effective_date=str(metadata["effective_date"]),
                    source=str(metadata["source"]),
                    section=str(metadata["section"]),
                    paragraph_id=str(metadata["paragraph_id"]),
                    content=content,
                    page=(int(metadata["page"]) if metadata.get("page") else None),
                )
                results.append(RetrievedChunk(chunk=chunk, score=1.0 - float(distance)))
            return results

        try:
            return await asyncio.to_thread(query_index)
        except ConfigurationError:
            raise
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise IntegrationError("制度向量检索失败") from exc

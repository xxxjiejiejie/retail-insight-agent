from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError, IntegrationError
from app.rag.models import RetrievedChunk


class BGEReranker:
    def __init__(self, settings: Settings):
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigurationError("缺少 sentence-transformers Reranker 依赖") from exc

        cache_folder = settings.model_cache_path or None
        self._model: Any = CrossEncoder(
            settings.reranker_model,
            cache_folder=cache_folder,
            local_files_only=settings.model_local_files_only,
            max_length=512,
        )

    @classmethod
    def from_settings(cls) -> BGEReranker:
        return cls(get_settings())

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        *,
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        def predict() -> list[RetrievedChunk]:
            pairs = [(query, candidate.chunk.content) for candidate in candidates]
            scores = self._model.predict(pairs, show_progress_bar=False)
            rescored = [
                RetrievedChunk(chunk=candidate.chunk, score=float(score))
                for candidate, score in zip(candidates, scores, strict=True)
            ]
            return sorted(rescored, key=lambda item: item.score, reverse=True)[:top_k]

        try:
            return await asyncio.to_thread(predict)
        except (RuntimeError, TypeError, ValueError) as exc:
            raise IntegrationError("制度证据重排失败") from exc

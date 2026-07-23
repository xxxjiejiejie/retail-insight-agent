from __future__ import annotations

import asyncio
import json
import math
import re
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Any

from app.core.errors import ConfigurationError, IntegrationError
from app.rag.models import DocumentChunk, RetrievedChunk

ASCII_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
CJK_SEQUENCE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def tokenize_for_bm25(text: str) -> list[str]:
    normalized = text.lower()
    tokens = ASCII_WORD_PATTERN.findall(normalized)
    for match in CJK_SEQUENCE_PATTERN.finditer(normalized):
        sequence = match.group(0)
        tokens.extend(sequence)
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


class BM25PolicyRetriever:
    def __init__(
        self,
        chunks: list[DocumentChunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        if not chunks:
            raise ConfigurationError("BM25 语料为空，请先运行制度索引脚本")
        self._chunks = chunks
        self._k1 = k1
        self._b = b
        self._term_frequencies = [Counter(tokenize_for_bm25(chunk.content)) for chunk in chunks]
        self._document_lengths = [
            sum(frequencies.values()) for frequencies in self._term_frequencies
        ]
        self._average_length = sum(self._document_lengths) / len(self._document_lengths)
        document_frequencies: Counter[str] = Counter()
        for frequencies in self._term_frequencies:
            document_frequencies.update(frequencies.keys())
        document_count = len(chunks)
        self._idf = {
            term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequencies.items()
        }

    @classmethod
    def from_corpus(cls, path: Path) -> BM25PolicyRetriever:
        if not path.exists():
            raise ConfigurationError(f"BM25 语料不存在，请先运行制度索引脚本：{path}")
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
            raw_chunks = raw["chunks"]
            allowed_fields = {field.name for field in fields(DocumentChunk)}
            chunks = [
                DocumentChunk(
                    **{key: value for key, value in item.items() if key in allowed_fields}
                )
                for item in raw_chunks
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"BM25 语料格式错误：{path}") from exc
        return cls(chunks)

    def _score(self, query: str) -> list[float]:
        query_terms = set(tokenize_for_bm25(query))
        scores: list[float] = []
        for frequencies, document_length in zip(
            self._term_frequencies,
            self._document_lengths,
            strict=True,
        ):
            score = 0.0
            length_ratio = document_length / self._average_length if self._average_length else 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + self._k1 * (1 - self._b + self._b * length_ratio)
                score += self._idf.get(term, 0.0) * frequency * (self._k1 + 1) / denominator
            scores.append(score)
        return scores

    async def retrieve(self, query: str, *, top_k: int) -> list[RetrievedChunk]:
        def rank() -> list[RetrievedChunk]:
            scores = self._score(query)
            ranked_indices = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
            return [
                RetrievedChunk(chunk=self._chunks[index], score=scores[index])
                for index in ranked_indices[:top_k]
                if scores[index] > 0
            ]

        try:
            return await asyncio.to_thread(rank)
        except (RuntimeError, TypeError, ValueError) as exc:
            raise IntegrationError("BM25 制度检索失败") from exc

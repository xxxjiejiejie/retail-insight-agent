from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DocumentSection:
    title: str
    content: str
    page: int | None = None


@dataclass(slots=True, frozen=True)
class PolicyDocument:
    document_id: str
    title: str
    version: str
    effective_date: str
    source: str
    content: str
    sections: tuple[DocumentSection, ...] = ()


@dataclass(slots=True, frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    title: str
    version: str
    effective_date: str
    source: str
    section: str
    paragraph_id: str
    content: str
    page: int | None = None


@dataclass(slots=True, frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float

    def to_context(self, index: int) -> str:
        return (
            f"[{index}] 文档：{self.chunk.title}\n"
            f"版本：{self.chunk.version}\n"
            f"章节：{self.chunk.section}\n"
            f"段落：{self.chunk.paragraph_id}\n"
            f"内容：{self.chunk.content}"
        )

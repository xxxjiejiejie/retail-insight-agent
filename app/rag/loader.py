from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.rag.models import DocumentChunk, PolicyDocument

REQUIRED_METADATA = {"document_id", "title", "version", "effective_date"}
HEADING_PATTERN = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
SENTENCE_ENDINGS = "。！？；\n"


def _parse_frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError(f"制度文档缺少 YAML frontmatter：{source.name}")
    try:
        raw_metadata, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"制度文档 frontmatter 未闭合：{source.name}") from exc

    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"制度文档元数据格式错误：{source.name}")
        metadata[key.strip()] = value.strip().strip('"')

    missing = sorted(REQUIRED_METADATA - metadata.keys())
    if missing:
        raise ValueError(f"制度文档缺少元数据 {', '.join(missing)}：{source.name}")
    return metadata, body.strip()


def load_policy_document(path: Path) -> PolicyDocument:
    metadata, body = _parse_frontmatter(path.read_text(encoding="utf-8"), path)
    return PolicyDocument(
        document_id=metadata["document_id"],
        title=metadata["title"],
        version=metadata["version"],
        effective_date=metadata["effective_date"],
        source=path.name,
        content=body,
    )


def load_policy_documents(directory: Path) -> list[PolicyDocument]:
    paths = sorted(path for path in directory.glob("*.md") if path.name.lower() != "readme.md")
    documents = [load_policy_document(path) for path in paths]
    identifiers = [document.document_id for document in documents]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("制度文档 document_id 不能重复")
    return documents


def _section_blocks(content: str) -> list[tuple[str, str]]:
    current_section = "总则"
    current_lines: list[str] = []
    blocks: list[tuple[str, str]] = []
    for line in content.splitlines():
        heading = HEADING_PATTERN.match(line)
        if heading:
            section_text = "\n".join(current_lines).strip()
            if section_text:
                blocks.append((current_section, section_text))
            current_section = heading.group(2).strip()
            current_lines = []
        elif line.startswith("# "):
            continue
        else:
            current_lines.append(line)
    section_text = "\n".join(current_lines).strip()
    if section_text:
        blocks.append((current_section, section_text))
    return blocks


def _split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    compact = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(compact) <= max_chars:
        return [compact]

    parts: list[str] = []
    start = 0
    while start < len(compact):
        hard_end = min(start + max_chars, len(compact))
        end = hard_end
        if hard_end < len(compact):
            minimum_end = start + max_chars // 2
            candidates = [compact.rfind(mark, minimum_end, hard_end) for mark in SENTENCE_ENDINGS]
            sentence_end = max(candidates)
            if sentence_end >= minimum_end:
                end = sentence_end + 1
        part = compact[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(compact):
            break
        start = max(end - overlap_chars, start + 1)
    return parts


def chunk_policy_document(
    document: PolicyDocument,
    *,
    max_chars: int = 700,
    overlap_chars: int = 80,
) -> list[DocumentChunk]:
    if max_chars < 200:
        raise ValueError("max_chars 不能小于 200")
    if overlap_chars < 0 or overlap_chars >= max_chars // 2:
        raise ValueError("overlap_chars 必须大于等于 0 且小于 max_chars 的一半")

    chunks: list[DocumentChunk] = []
    for section_index, (section, section_text) in enumerate(_section_blocks(document.content), 1):
        for part_index, part in enumerate(
            _split_text(section_text, max_chars, overlap_chars),
            1,
        ):
            paragraph_id = f"{document.document_id}-S{section_index:02d}-P{part_index:02d}"
            digest_input = f"{document.document_id}|{section}|{paragraph_id}|{part}"
            chunk_id = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:20]
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    title=document.title,
                    version=document.version,
                    effective_date=document.effective_date,
                    source=document.source,
                    section=section,
                    paragraph_id=paragraph_id,
                    content=part,
                )
            )
    return chunks


def load_and_chunk_policies(
    directory: Path,
    *,
    max_chars: int = 700,
    overlap_chars: int = 80,
) -> list[DocumentChunk]:
    return [
        chunk
        for document in load_policy_documents(directory)
        for chunk in chunk_policy_document(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
    ]

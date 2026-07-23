from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.rag.loader import chunk_policy_document, discover_policy_paths, load_policy_document
from app.rag.models import DocumentChunk

INDEX_FORMAT_VERSION = 1


@dataclass(slots=True, frozen=True)
class SourceIndexEntry:
    digest: str
    document_id: str
    chunk_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class IndexSnapshot:
    entries: dict[str, SourceIndexEntry]
    chunks: tuple[DocumentChunk, ...]


@dataclass(slots=True, frozen=True)
class IncrementalIndexPlan:
    changed_sources: tuple[str, ...]
    deleted_sources: tuple[str, ...]
    unchanged_sources: tuple[str, ...]
    chunks_to_upsert: tuple[DocumentChunk, ...]
    chunk_ids_to_delete: tuple[str, ...]


def _source_digest(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes())
    sidecar = path.with_suffix(f"{path.suffix}.metadata.json")
    if sidecar.exists():
        digest.update(b"\0metadata\0")
        digest.update(sidecar.read_bytes())
    return digest.hexdigest()


def build_index_snapshot(
    directory: Path,
    *,
    max_chars: int = 700,
    overlap_chars: int = 80,
) -> IndexSnapshot:
    entries: dict[str, SourceIndexEntry] = {}
    chunks: list[DocumentChunk] = []
    identifiers: set[str] = set()
    for path in discover_policy_paths(directory):
        source = path.relative_to(directory).as_posix()
        document = load_policy_document(path)
        if document.document_id in identifiers:
            raise ValueError(f"制度文档 document_id 不能重复：{document.document_id}")
        identifiers.add(document.document_id)
        document = replace(document, source=source)
        document_chunks = chunk_policy_document(
            document,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )
        chunks.extend(document_chunks)
        entries[source] = SourceIndexEntry(
            digest=_source_digest(path),
            document_id=document.document_id,
            chunk_ids=tuple(chunk.chunk_id for chunk in document_chunks),
        )
    if not entries:
        raise ValueError(f"制度文档目录为空：{directory}")
    return IndexSnapshot(entries=entries, chunks=tuple(chunks))


def load_index_manifest(path: Path) -> dict[str, SourceIndexEntry]:
    if not path.exists():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"索引清单不是有效 JSON：{path}") from exc
    if not isinstance(raw, dict) or raw.get("format_version") != INDEX_FORMAT_VERSION:
        raise ValueError(f"索引清单版本不兼容：{path}")
    sources = raw.get("sources")
    if not isinstance(sources, dict):
        raise ValueError(f"索引清单缺少 sources：{path}")
    entries: dict[str, SourceIndexEntry] = {}
    for source, entry in sources.items():
        if not isinstance(entry, dict):
            raise ValueError(f"索引清单条目格式错误：{source}")
        entries[str(source)] = SourceIndexEntry(
            digest=str(entry["digest"]),
            document_id=str(entry["document_id"]),
            chunk_ids=tuple(str(item) for item in entry["chunk_ids"]),
        )
    return entries


def plan_incremental_index(
    snapshot: IndexSnapshot,
    previous: dict[str, SourceIndexEntry],
    *,
    full_rebuild: bool = False,
) -> IncrementalIndexPlan:
    current_sources = set(snapshot.entries)
    previous_sources = set(previous)
    if full_rebuild:
        changed = current_sources
        deleted = previous_sources - current_sources
        unchanged: set[str] = set()
    else:
        changed = {
            source
            for source, entry in snapshot.entries.items()
            if source not in previous or previous[source].digest != entry.digest
        }
        deleted = previous_sources - current_sources
        unchanged = current_sources - changed
    chunks_to_upsert = tuple(chunk for chunk in snapshot.chunks if chunk.source in changed)
    replaced_sources = changed | deleted
    chunk_ids_to_delete = tuple(
        chunk_id
        for source in sorted(replaced_sources & previous_sources)
        for chunk_id in previous[source].chunk_ids
    )
    return IncrementalIndexPlan(
        changed_sources=tuple(sorted(changed)),
        deleted_sources=tuple(sorted(deleted)),
        unchanged_sources=tuple(sorted(unchanged)),
        chunks_to_upsert=chunks_to_upsert,
        chunk_ids_to_delete=chunk_ids_to_delete,
    )


def write_index_artifacts(
    snapshot: IndexSnapshot,
    *,
    manifest_path: Path,
    corpus_path: Path,
) -> None:
    manifest = {
        "format_version": INDEX_FORMAT_VERSION,
        "sources": {
            source: {
                "digest": entry.digest,
                "document_id": entry.document_id,
                "chunk_ids": list(entry.chunk_ids),
            }
            for source, entry in sorted(snapshot.entries.items())
        },
    }
    corpus = {
        "format_version": INDEX_FORMAT_VERSION,
        "chunks": [asdict(chunk) for chunk in snapshot.chunks],
    }
    for path, payload in ((manifest_path, manifest), (corpus_path, corpus)):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

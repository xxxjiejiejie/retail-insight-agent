"""Incrementally update Chroma and the BM25 corpus for policy documents."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.rag.indexing import (
    build_index_snapshot,
    load_index_manifest,
    plan_incremental_index,
    write_index_artifacts,
)
from app.rag.vector_store import ChromaPolicyRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
MANIFEST_PATH = PROJECT_ROOT / "data" / "runtime" / "policy_index_manifest.json"
CORPUS_PATH = PROJECT_ROOT / "data" / "runtime" / "bm25_corpus.json"


async def main(*, full_rebuild: bool = False) -> None:
    snapshot = build_index_snapshot(DOCUMENTS_DIR)
    previous = load_index_manifest(MANIFEST_PATH)
    plan = plan_incremental_index(snapshot, previous, full_rebuild=full_rebuild)
    if full_rebuild:
        retriever = ChromaPolicyRetriever.from_settings()
        indexed_count = await retriever.replace_index(list(snapshot.chunks))
        deleted_count = sum(len(entry.chunk_ids) for entry in previous.values())
    elif plan.chunks_to_upsert or plan.chunk_ids_to_delete:
        retriever = ChromaPolicyRetriever.from_settings()
        deleted_count = await retriever.delete_chunks(list(plan.chunk_ids_to_delete))
        indexed_count = await retriever.upsert_chunks(list(plan.chunks_to_upsert))
    else:
        deleted_count = 0
        indexed_count = 0
    write_index_artifacts(snapshot, manifest_path=MANIFEST_PATH, corpus_path=CORPUS_PATH)
    print(
        f"documents={len(snapshot.entries)} chunks={len(snapshot.chunks)} "
        f"changed={len(plan.changed_sources)} deleted_sources={len(plan.deleted_sources)} "
        f"upserted={indexed_count} removed_chunks={deleted_count} index_status=ready"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full-rebuild", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(main(full_rebuild=arguments.full_rebuild))

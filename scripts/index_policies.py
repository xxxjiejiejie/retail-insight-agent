"""Build a replaceable local Chroma index for the simulated policy documents."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.rag.loader import load_and_chunk_policies
from app.rag.vector_store import ChromaPolicyRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"


async def main() -> None:
    chunks = load_and_chunk_policies(DOCUMENTS_DIR)
    retriever = ChromaPolicyRetriever.from_settings()
    indexed_count = await retriever.replace_index(chunks)
    print(f"documents=8 chunks={indexed_count} index_status=ready")


if __name__ == "__main__":
    asyncio.run(main())

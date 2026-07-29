from pathlib import Path

import pytest

from app.rag.loader import chunk_policy_document, load_policy_document, load_policy_documents

DOCUMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "documents"


def test_loads_expanded_policy_documents_with_unique_ids() -> None:
    documents = load_policy_documents(DOCUMENTS_DIR)

    assert len(documents) == 100
    assert len({document.document_id for document in documents}) == 100
    assert all(document.version == "1.0" for document in documents)


def test_chunk_ids_are_stable_and_content_is_bounded() -> None:
    document = load_policy_document(DOCUMENTS_DIR / "promotion_approval_policy.md")

    first = chunk_policy_document(document, max_chars=300, overlap_chars=50)
    second = chunk_policy_document(document, max_chars=300, overlap_chars=50)

    assert first == second
    assert first
    assert all(len(chunk.content) <= 300 for chunk in first)
    assert len({chunk.chunk_id for chunk in first}) == len(first)
    assert all(chunk.paragraph_id.startswith("POL-PROMO-001-") for chunk in first)


def test_rejects_invalid_chunk_overlap() -> None:
    document = load_policy_document(DOCUMENTS_DIR / "return_exchange_policy.md")

    with pytest.raises(ValueError, match="overlap_chars"):
        chunk_policy_document(document, max_chars=300, overlap_chars=150)

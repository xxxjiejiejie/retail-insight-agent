"""Validate the local policy corpus and write a reproducible corpus summary."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from app.rag.loader import load_and_chunk_policies, load_policy_documents

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
REPORT_PATH = PROJECT_ROOT / "data" / "runtime" / "policy_corpus_report.json"
SEED_DOCUMENT_IDS = {
    "POL-RETURN-001",
    "POL-PROMO-001",
    "POL-INVENTORY-001",
    "POL-MEMBER-001",
    "POL-PRIVACY-001",
    "POL-PERFORMANCE-001",
    "POL-PRICE-001",
    "POL-ORDER-001",
}


def _domain(document_id: str) -> str:
    match = re.fullmatch(r"POL-([A-Z]+)-\d{3}", document_id)
    if match is None:
        raise ValueError(f"document_id 格式不符合约定：{document_id}")
    return match.group(1)


def validate_corpus(
    documents_directory: Path = DOCUMENTS_DIR,
    report_path: Path = REPORT_PATH,
) -> dict[str, object]:
    documents = load_policy_documents(documents_directory)
    chunks = load_and_chunk_policies(documents_directory)
    document_ids = [document.document_id for document in documents]
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    paragraph_ids = [chunk.paragraph_id for chunk in chunks]
    normalized_bodies = [" ".join(document.content.split()) for document in documents]
    body_counts = Counter(normalized_bodies)
    duplicate_document_count = sum(count - 1 for count in body_counts.values() if count > 1)
    source_hash = hashlib.sha256()
    for document in sorted(documents, key=lambda item: item.source):
        source_hash.update(document.source.encode("utf-8"))
        source_hash.update(document.content.encode("utf-8"))

    if not 95 <= len(documents) <= 105:
        raise ValueError(f"制度文档数量应接近 100，实际为 {len(documents)}")
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("document_id 存在重复")
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk_id 存在重复")
    if len(paragraph_ids) != len(set(paragraph_ids)):
        raise ValueError("paragraph_id 存在重复")
    if duplicate_document_count:
        raise ValueError(f"发现 {duplicate_document_count} 份正文完全重复的制度")

    domain_distribution = dict(sorted(Counter(_domain(item) for item in document_ids).items()))
    report: dict[str, object] = {
        "corpus_version": source_hash.hexdigest()[:16],
        "document_count": len(documents),
        "seed_document_count": sum(item in SEED_DOCUMENT_IDS for item in document_ids),
        "expanded_document_count": sum(item not in SEED_DOCUMENT_IDS for item in document_ids),
        "chunk_count": len(chunks),
        "domain_count": len(domain_distribution),
        "domain_distribution": domain_distribution,
        "unique_document_ids": len(set(document_ids)),
        "unique_chunk_ids": len(set(chunk_ids)),
        "unique_paragraph_ids": len(set(paragraph_ids)),
        "exact_duplicate_document_count": duplicate_document_count,
        "min_chunks_per_document": min(Counter(chunk.document_id for chunk in chunks).values()),
        "max_chunks_per_document": max(Counter(chunk.document_id for chunk in chunks).values()),
        "description": "100 份原创模拟零售制度/SOP，用于本地检索评测，不代表生产企业制度库。",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = validate_corpus()
    print(
        f"documents={report['document_count']} chunks={report['chunk_count']} "
        f"domains={report['domain_count']} report={REPORT_PATH}"
    )


if __name__ == "__main__":
    main()

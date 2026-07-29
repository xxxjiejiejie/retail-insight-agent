"""Build chunk-level RAG ground truth from policy authorship, never retrieval ranks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.rag.loader import load_and_chunk_policies, load_policy_documents
from app.rag.models import DocumentChunk, PolicyDocument

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
TARGET_PATH = PROJECT_ROOT / "data" / "eval" / "rag_ground_truth.json"
DOMAINS = (
    "RETURN",
    "PROMO",
    "INVENTORY",
    "MEMBER",
    "PRIVACY",
    "PERFORMANCE",
    "PRICE",
    "ORDER",
    "STORE",
    "PROCUREMENT",
)
NEGATIVE_QUESTIONS = (
    "公司无人机配送的飞行高度上限是多少？",
    "海外门店使用哪一种加密货币结算？",
    "员工宿舍宠物饲养需要缴纳多少押金？",
    "工厂机器人焊接参数由哪个岗位审批？",
    "公司班车周末最晚一班几点发车？",
    "自建数据中心的液冷温度标准是多少？",
    "海外仓海运保险的免赔额是多少？",
    "直播主播的个人服装补贴标准是多少？",
    "门店屋顶光伏的并网电压是多少？",
    "公司航空货运包机每月可以申请几次？",
)


def _relevant_chunks(
    chunks_by_document: dict[str, list[DocumentChunk]],
    document_id: str,
) -> list[dict[str, Any]]:
    candidates = [
        chunk
        for chunk in chunks_by_document[document_id]
        if chunk.section == "核心规则"
    ]
    if not candidates:
        raise ValueError(f"{document_id} 缺少“核心规则”分块")
    return [
        {
            "chunk_id": chunk.chunk_id,
            "paragraph_id": chunk.paragraph_id,
            "document_id": chunk.document_id,
            "relevance": 2,
        }
        for chunk in candidates
    ]


def build_ground_truth(
    documents_directory: Path = DOCUMENTS_DIR,
    target_path: Path = TARGET_PATH,
) -> dict[str, Any]:
    documents = load_policy_documents(documents_directory)
    chunks = load_and_chunk_policies(documents_directory)
    documents_by_id: dict[str, PolicyDocument] = {
        document.document_id: document for document in documents
    }
    chunks_by_document: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        chunks_by_document.setdefault(chunk.document_id, []).append(chunk)

    cases: list[dict[str, Any]] = []
    direct_number = 0
    for domain in DOMAINS:
        for sequence in range(2, 8):
            document_id = f"POL-{domain}-{sequence:03d}"
            document = documents_by_id[document_id]
            direct_number += 1
            cases.append(
                {
                    "id": f"rag-direct-{direct_number:03d}",
                    "split": "dev" if direct_number <= 20 else "test",
                    "category": "direct_fact",
                    "question": f"《{document.title}》由谁发起，常规处理时限是多少？",
                    "expect_answer": True,
                    "expected_document_ids": [document_id],
                    "relevant_chunks": _relevant_chunks(chunks_by_document, document_id),
                }
            )

    for index, domain in enumerate(DOMAINS):
        first_id = f"POL-{domain}-008"
        second_id = f"POL-{DOMAINS[(index + 1) % len(DOMAINS)]}-009"
        first = documents_by_id[first_id]
        second = documents_by_id[second_id]
        cases.append(
            {
                "id": f"rag-cross-{index + 1:03d}",
                "split": "dev" if index < 4 else "test",
                "category": "cross_document",
                "question": (
                    f"比较《{first.title}》与《{second.title}》的审批门槛和复核要求。"
                ),
                "expect_answer": True,
                "expected_document_ids": [first_id, second_id],
                "relevant_chunks": [
                    *_relevant_chunks(chunks_by_document, first_id),
                    *_relevant_chunks(chunks_by_document, second_id),
                ],
            }
        )

    for index, question in enumerate(NEGATIVE_QUESTIONS, 1):
        cases.append(
            {
                "id": f"rag-negative-{index:03d}",
                "split": "dev" if index <= 4 else "test",
                "category": "out_of_corpus",
                "question": question,
                "expect_answer": False,
                "expected_document_ids": [],
                "relevant_chunks": [],
            }
        )

    digest = hashlib.sha256(
        json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    payload = {
        "dataset_version": digest,
        "description": (
            "基于制度编写结构人工规则生成的 chunk 级 Ground Truth，"
            "未使用检索排名反向标注。"
        ),
        "case_count": len(cases),
        "answerable_case_count": sum(bool(case["expect_answer"]) for case in cases),
        "negative_case_count": sum(not bool(case["expect_answer"]) for case in cases),
        "cases": cases,
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = build_ground_truth()
    print(
        f"cases={payload['case_count']} answerable={payload['answerable_case_count']} "
        f"negative={payload['negative_case_count']} report={TARGET_PATH}"
    )


if __name__ == "__main__":
    main()

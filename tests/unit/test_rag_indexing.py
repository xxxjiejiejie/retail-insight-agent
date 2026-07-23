from __future__ import annotations

from pathlib import Path

from app.rag.indexing import (
    build_index_snapshot,
    plan_incremental_index,
    write_index_artifacts,
)


def write_policy(path: Path, *, document_id: str, body: str) -> None:
    path.write_text(
        "\n".join(
            [
                "---",
                f"document_id: {document_id}",
                f"title: {document_id} 制度",
                "version: 1.0",
                "effective_date: 2026-07-01",
                "---",
                f"# {document_id} 制度",
                "",
                "## 规则",
                "",
                body,
            ]
        ),
        encoding="utf-8",
    )


def test_incremental_plan_only_upserts_changed_sources(tmp_path: Path) -> None:
    first_path = tmp_path / "first.md"
    second_path = tmp_path / "second.md"
    write_policy(first_path, document_id="POL-ONE", body="第一份制度内容。")
    write_policy(second_path, document_id="POL-TWO", body="第二份制度内容。")
    first_snapshot = build_index_snapshot(tmp_path)

    initial_plan = plan_incremental_index(first_snapshot, {})
    assert set(initial_plan.changed_sources) == {"first.md", "second.md"}
    assert len(initial_plan.chunks_to_upsert) == 2

    previous = first_snapshot.entries
    unchanged_plan = plan_incremental_index(first_snapshot, previous)
    assert not unchanged_plan.changed_sources
    assert len(unchanged_plan.unchanged_sources) == 2

    write_policy(first_path, document_id="POL-ONE", body="第一份制度内容已修改。")
    changed_snapshot = build_index_snapshot(tmp_path)
    changed_plan = plan_incremental_index(changed_snapshot, previous)

    assert changed_plan.changed_sources == ("first.md",)
    assert changed_plan.chunks_to_upsert[0].document_id == "POL-ONE"
    assert changed_plan.chunk_ids_to_delete == previous["first.md"].chunk_ids


def test_incremental_plan_removes_deleted_sources(tmp_path: Path) -> None:
    policy_path = tmp_path / "obsolete.md"
    write_policy(policy_path, document_id="POL-OLD", body="即将废止的制度。")
    previous_snapshot = build_index_snapshot(tmp_path)
    policy_path.unlink()
    write_policy(tmp_path / "current.md", document_id="POL-NEW", body="现行制度。")
    current_snapshot = build_index_snapshot(tmp_path)

    plan = plan_incremental_index(current_snapshot, previous_snapshot.entries)

    assert plan.deleted_sources == ("obsolete.md",)
    assert set(plan.chunk_ids_to_delete) == set(previous_snapshot.entries["obsolete.md"].chunk_ids)


def test_writes_manifest_and_bm25_corpus_atomically(tmp_path: Path) -> None:
    write_policy(tmp_path / "policy.md", document_id="POL-ONE", body="制度内容。")
    snapshot = build_index_snapshot(tmp_path)
    manifest_path = tmp_path / "runtime" / "manifest.json"
    corpus_path = tmp_path / "runtime" / "corpus.json"

    write_index_artifacts(snapshot, manifest_path=manifest_path, corpus_path=corpus_path)

    assert manifest_path.exists()
    assert corpus_path.exists()
    assert not manifest_path.with_suffix(".json.tmp").exists()

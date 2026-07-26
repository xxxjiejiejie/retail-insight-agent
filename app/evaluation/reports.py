from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"评测报告必须是 JSON 数组：{path.name}")
    return [entry for entry in payload if isinstance(entry, dict)]


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 2)


def _entry_errors(entry: dict[str, Any]) -> list[str]:
    errors = entry.get("errors")
    if not isinstance(errors, list):
        return []
    return [str(error) for error in errors]


def _branch_summary(
    entries: list[dict[str, Any]],
    *,
    coverage: str,
) -> dict[str, Any]:
    passed = sum(bool(entry.get("passed")) for entry in entries)
    rejected = sum(bool(_entry_errors(entry)) for entry in entries)
    token_values: list[float] = []
    latency_values: list[float] = []
    for entry in entries:
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict):
            continue
        tokens = _as_number(metrics.get("total_tokens"))
        latency = _as_number(metrics.get("total_latency_ms"))
        if tokens is not None:
            token_values.append(tokens)
        if latency is not None:
            latency_values.append(latency)
    total = len(entries)
    total_tokens = round(sum(token_values))
    return {
        "passed": passed,
        "total": total,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "rejected": rejected,
        "rejection_rate": round(rejected / total, 4) if total else 0.0,
        "total_tokens": total_tokens,
        "avg_tokens": round(total_tokens / total, 2) if total else 0.0,
        "p50_latency_ms": _percentile(latency_values, 0.5),
        "p95_latency_ms": _percentile(latency_values, 0.95),
        "coverage": coverage,
    }


def _challenge_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(entry.get("passed")) for entry in entries)
    categories: dict[str, dict[str, Any]] = {}
    for category in sorted({str(entry.get("category") or "unknown") for entry in entries}):
        category_entries = [
            entry for entry in entries if str(entry.get("category") or "unknown") == category
        ]
        category_passed = sum(bool(entry.get("passed")) for entry in category_entries)
        categories[category] = {
            "passed": category_passed,
            "total": len(category_entries),
            "accuracy": round(category_passed / len(category_entries), 4),
        }
    return {
        "passed": passed,
        "total": len(entries),
        "accuracy": round(passed / len(entries), 4) if entries else 0.0,
        "categories": categories,
        "description": "SQL 边界、RAG 库外问题与 Prompt Injection 实际运行结果。",
    }


def _supplementary_summary(
    entries: list[dict[str, Any]],
    *,
    description: str,
) -> dict[str, Any]:
    passed = sum(bool(entry.get("passed")) for entry in entries)
    categories: dict[str, dict[str, Any]] = {}
    for category in sorted({str(entry.get("category") or "unknown") for entry in entries}):
        category_entries = [
            entry for entry in entries if str(entry.get("category") or "unknown") == category
        ]
        category_passed = sum(bool(entry.get("passed")) for entry in category_entries)
        categories[category] = {
            "passed": category_passed,
            "total": len(category_entries),
            "accuracy": round(category_passed / len(category_entries), 4),
        }
    return {
        "passed": passed,
        "total": len(entries),
        "accuracy": round(passed / len(entries), 4) if entries else 0.0,
        "categories": categories,
        "description": description,
    }


def _failure_diagnosis(branch: str, entry: dict[str, Any]) -> tuple[str, str]:
    errors = _entry_errors(entry)
    if branch == "sql":
        if errors:
            return "execution_error", "SQL 生成或执行阶段返回错误。"
        if entry.get("generated_row_count") != entry.get("reference_row_count"):
            return "row_count_mismatch", "生成结果行数与参考结果不一致。"
        return "result_mismatch", "生成结果值与参考查询结果不一致。"
    if branch == "rag":
        expected = set(entry.get("expected_document_ids") or [])
        actual = set(entry.get("cited_document_ids") or [])
        if entry.get("expect_answer") is False and actual:
            return "refusal_missed", "库外问题未正确拒答，返回了制度引用。"
        if entry.get("expect_answer") is True and errors:
            return "unexpected_refusal", "有证据问题被错误拒答或生成失败。"
        if not expected.issubset(actual):
            return "citation_missing", "引用未覆盖预期制度文档。"
        return "rag_answer_failed", "RAG 回答未满足评测条件。"
    sql_passed = bool(entry.get("sql_passed"))
    citation_passed = bool(entry.get("citation_passed"))
    if not sql_passed and not citation_passed:
        return "hybrid_both_failed", "SQL 结果和制度引用均未通过。"
    if not sql_passed:
        return "hybrid_sql_failed", "Hybrid 的 SQL 子问题结果未通过。"
    if not citation_passed:
        return "hybrid_citation_failed", "Hybrid 的制度引用未通过。"
    return "hybrid_merge_failed", "子分支通过，但合并结果包含错误。"


def _failure_sample(branch: str, entry: dict[str, Any]) -> dict[str, Any]:
    failure_type, diagnosis = _failure_diagnosis(branch, entry)
    raw_metrics = entry.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    expected: dict[str, Any]
    actual: dict[str, Any]
    if branch == "sql":
        expected = {"row_count": entry.get("reference_row_count")}
        actual = {"row_count": entry.get("generated_row_count")}
    elif branch == "rag":
        expected = {
            "expect_answer": entry.get("expect_answer"),
            "document_ids": entry.get("expected_document_ids") or [],
        }
        actual = {
            "document_ids": entry.get("cited_document_ids") or [],
            "refused": bool(_entry_errors(entry)),
        }
    else:
        expected = {
            "sql_passed": True,
            "document_ids": entry.get("expected_document_ids") or [],
        }
        actual = {
            "sql_passed": bool(entry.get("sql_passed")),
            "citation_passed": bool(entry.get("citation_passed")),
            "document_ids": entry.get("cited_document_ids") or [],
        }
    return {
        "case_id": str(entry.get("id") or "unknown"),
        "branch": branch,
        "set_type": "normal",
        "failure_type": failure_type,
        "diagnosis": diagnosis,
        "question": str(entry.get("question") or ""),
        "expected": expected,
        "actual": actual,
        "errors": _entry_errors(entry),
        "generated_sql": entry.get("generated_sql"),
        "total_tokens": _as_number(metrics.get("total_tokens")),
        "latency_ms": _as_number(metrics.get("total_latency_ms")),
    }


def _challenge_failure_sample(entry: dict[str, Any]) -> dict[str, Any]:
    category = str(entry.get("category") or "challenge_failed")
    diagnoses = {
        "sql_boundary": "SQL 边界条件结果未匹配参考查询。",
        "rag_out_of_scope": "库外问题未正确拒答。",
        "prompt_injection": "Prompt Injection 防护条件未全部满足。",
    }
    raw_metrics = entry.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    expected = entry.get("expected")
    actual = entry.get("actual")
    return {
        "case_id": str(entry.get("id") or "unknown"),
        "branch": str(entry.get("branch") or "rag"),
        "set_type": "challenge",
        "failure_type": category,
        "diagnosis": diagnoses.get(category, "挑战样本未满足预期条件。"),
        "question": str(entry.get("question") or ""),
        "expected": expected if isinstance(expected, dict) else {},
        "actual": actual if isinstance(actual, dict) else {},
        "errors": _entry_errors(entry),
        "generated_sql": entry.get("generated_sql"),
        "total_tokens": _as_number(metrics.get("total_tokens")),
        "latency_ms": _as_number(metrics.get("total_latency_ms")),
    }


def _supplementary_failure_sample(entry: dict[str, Any]) -> dict[str, Any]:
    set_type = str(entry.get("set_type") or "supplementary")
    raw_metrics = entry.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    if set_type == "multi_turn":
        expected = {
            "context_used": True,
            "intent": entry.get("branch"),
            "sql_passed": True,
            "document_ids": entry.get("expected_document_ids") or [],
        }
        actual = {
            "context_used": bool(entry.get("context_passed")),
            "intent_passed": bool(entry.get("intent_passed")),
            "sql_passed": bool(entry.get("sql_passed")),
            "document_ids": entry.get("cited_document_ids") or [],
        }
        diagnosis = "多轮追问的上下文、路由、SQL 结果或制度引用未全部通过。"
    else:
        expected = {"recovered_safely": True}
        actual = {
            "recovered_safely": bool(entry.get("passed")),
            "recovery": entry.get("recovery"),
        }
        diagnosis = "故障恢复场景未满足安全降级或自动修复条件。"
    return {
        "case_id": str(entry.get("id") or "unknown"),
        "branch": str(entry.get("branch") or "sql"),
        "set_type": set_type,
        "failure_type": str(entry.get("category") or f"{set_type}_failed"),
        "diagnosis": diagnosis,
        "question": str(entry.get("question") or ""),
        "expected": expected,
        "actual": actual,
        "errors": _entry_errors(entry),
        "generated_sql": entry.get("generated_sql"),
        "total_tokens": _as_number(metrics.get("total_tokens")),
        "latency_ms": _as_number(metrics.get("total_latency_ms")),
    }
def _dataset_version(eval_directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(eval_directory.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _git_metadata(project_root: Path) -> tuple[str | None, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        return commit or None, "dirty" if status else "clean"
    except (OSError, subprocess.SubprocessError):
        return None, "unknown"


def _quality_gate(report_directory: Path) -> dict[str, Any] | None:
    path = report_directory / "comprehensive_eval_report.json"
    if not path.exists():
        return None
    payload = _load_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise ValueError("综合评测报告格式无效")
    summary = payload["summary"]
    return {
        "passed": int(summary.get("passed", 0)),
        "total": int(summary.get("total", 0)),
        "accuracy": float(summary.get("pass_rate", 0.0)),
        "duration_ms": _as_number(payload.get("duration_ms")),
        "categories": summary.get("categories", {}),
    }


def _known_limitations(eval_directory: Path) -> list[dict[str, str]]:
    path = eval_directory / "known_limitations.json"
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError("已知限制清单必须是 JSON 数组")
    limitations: list[dict[str, str]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        limitations.append(
            {
                "id": str(entry.get("id") or "unknown"),
                "title": str(entry.get("title") or "未命名限制"),
                "description": str(entry.get("description") or ""),
                "status": str(entry.get("status") or "open"),
            }
        )
    return limitations


def _improvements(eval_directory: Path) -> list[dict[str, str]]:
    path = eval_directory / "improvements.json"
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, list):
        raise ValueError("优化说明必须是 JSON 数组")
    improvements: list[dict[str, str]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        improvements.append(
            {
                "id": str(entry.get("id") or "unknown"),
                "title": str(entry.get("title") or "未命名优化"),
                "problem": str(entry.get("problem") or ""),
                "change": str(entry.get("change") or ""),
                "evidence": str(entry.get("evidence") or ""),
                "status": str(entry.get("status") or "verified"),
            }
        )
    return improvements


def build_evaluation_run(
    *,
    project_root: Path,
    report_directory: Path,
    eval_directory: Path,
    label: str,
    model: str,
    run_id: str | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    run_id = run_id or generated_at.strftime("run-%Y%m%dT%H%M%SZ")
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("run_id 只能包含字母、数字、点、下划线和连字符")

    sql_path = report_directory / "sql_smoke_report.json"
    rag_path = report_directory / "rag_eval_report.json"
    hybrid_default = report_directory / "hybrid_live_report.json"
    challenge_path = report_directory / "challenge_eval_report.json"
    multiturn_path = report_directory / "multiturn_live_report.json"
    resilience_path = report_directory / "resilience_eval_report.json"
    hybrid_paths = (
        [hybrid_default]
        if hybrid_default.exists()
        else sorted(report_directory.glob("hybrid_live_*_report.json"))
    )
    sql_entries = _report_entries(sql_path)
    rag_entries = _report_entries(rag_path)
    hybrid_by_id: dict[str, dict[str, Any]] = {}
    for path in hybrid_paths:
        for entry in _report_entries(path):
            hybrid_by_id[str(entry.get("id") or path.stem)] = entry
    hybrid_entries = list(hybrid_by_id.values())
    challenge_entries = _report_entries(challenge_path)
    multiturn_entries = _report_entries(multiturn_path)
    resilience_entries = _report_entries(resilience_path)

    branches = {
        "sql": _branch_summary(sql_entries, coverage="真实模型 SQL 结果比对"),
        "rag": _branch_summary(rag_entries, coverage="真实模型引用与拒答评测"),
        "hybrid": _branch_summary(hybrid_entries, coverage="真实模型双分支抽样"),
    }
    failures = [
        _failure_sample(branch, entry)
        for branch, entries in (
            ("sql", sql_entries),
            ("rag", rag_entries),
            ("hybrid", hybrid_entries),
        )
        for entry in entries
        if not bool(entry.get("passed"))
    ]
    failures.extend(
        _challenge_failure_sample(entry)
        for entry in challenge_entries
        if not bool(entry.get("passed"))
    )
    failures.extend(
        _supplementary_failure_sample(entry)
        for entries in (multiturn_entries, resilience_entries)
        for entry in entries
        if not bool(entry.get("passed"))
    )
    total_cases = sum(branch["total"] for branch in branches.values())
    total_passed = sum(branch["passed"] for branch in branches.values())
    commit, workspace_state = _git_metadata(project_root)
    source_paths = [
        sql_path,
        rag_path,
        *hybrid_paths,
        challenge_path,
        multiturn_path,
        resilience_path,
    ]
    source_reports = [path.name for path in source_paths if path.exists()]
    notes = ["本地 100 项质量门禁不计入 SQL/RAG/Hybrid 端到端准确率。"]
    if len(sql_entries) < 30:
        notes.append(f"当前 SQL 真实报告仅保留 {len(sql_entries)} 条样本。")
    if len(hybrid_entries) < 5:
        notes.append(f"当前 Hybrid 真实报告仅保留 {len(hybrid_entries)} 条抽样。")
    notes.append("SQL/RAG/Hybrid 主指标只统计正常集；挑战集单独统计，不混入主准确率。")
    challenge_summary = _challenge_summary(challenge_entries)
    return {
        "run_id": run_id,
        "label": label.strip() or run_id,
        "generated_at": generated_at.isoformat(),
        "model": model,
        "dataset_version": _dataset_version(eval_directory),
        "git_commit": commit,
        "workspace_state": workspace_state,
        "total_cases": total_cases,
        "total_passed": total_passed,
        "overall_accuracy": round(total_passed / total_cases, 4) if total_cases else 0.0,
        "failure_count": len(failures),
        "branches": branches,
        "evaluation_sets": {
            "normal": {
                "passed": total_passed,
                "total": total_cases,
                "accuracy": round(total_passed / total_cases, 4) if total_cases else 0.0,
                "categories": {
                    branch: {
                        "passed": summary["passed"],
                        "total": summary["total"],
                        "accuracy": summary["accuracy"],
                    }
                    for branch, summary in branches.items()
                },
                "description": "SQL、RAG 与 Hybrid 端到端正常业务问题。",
            },
            "challenge": challenge_summary,
            "multi_turn": _supplementary_summary(
                multiturn_entries,
                description="真实模型双轮上下文追问，单独统计，不混入正常集主准确率。",
            ),
            "resilience": _supplementary_summary(
                resilience_entries,
                description="LLM 超时、格式异常和数据库超时的确定性故障恢复演示。",
            ),
        },
        "known_limitations": _known_limitations(eval_directory),
        "improvements": _improvements(eval_directory),
        "quality_gate": _quality_gate(report_directory),
        "failures": failures,
        "source_reports": source_reports,
        "notes": notes,
    }


def save_evaluation_run(run: dict[str, Any], run_directory: Path) -> Path:
    run_id = str(run.get("run_id") or "")
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError("评测批次缺少有效 run_id")
    run_directory.mkdir(parents=True, exist_ok=True)
    target = run_directory / f"{run_id}.json"
    if target.exists():
        raise FileExistsError(f"评测批次已存在：{run_id}")
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target


def load_evaluation_runs(run_directory: Path) -> list[dict[str, Any]]:
    if not run_directory.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in run_directory.glob("*.json"):
        payload = _load_json(path)
        if isinstance(payload, dict) and RUN_ID_PATTERN.fullmatch(str(payload.get("run_id") or "")):
            runs.append(payload)
    return sorted(runs, key=lambda run: str(run.get("generated_at") or ""), reverse=True)


def load_evaluation_run(run_directory: Path, run_id: str) -> dict[str, Any] | None:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        return None
    path = run_directory / f"{run_id}.json"
    if not path.exists():
        return None
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else None

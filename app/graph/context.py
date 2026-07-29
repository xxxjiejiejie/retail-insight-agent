from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CONTEXT_PREFIXES = (
    "那",
    "这个",
    "这些",
    "上述",
    "刚才",
    "前面",
    "同样",
    "换成",
    "改成",
    "再看",
    "只看",
    "仅看",
    "那么",
    "其中",
)
ANALYTICAL_INTENTS = {"sql", "rag", "hybrid"}
REPORT_SOURCE_INTENTS = {"sql", "hybrid"}
REPORT_PHRASES = (
    "生成报告",
    "生成一个报告",
    "生成一份报告",
    "生成分析报告",
    "形成报告",
    "形成简报",
    "导出报告",
    "写一份报告",
    "整理成报告",
    "出一份报告",
)


@dataclass(slots=True, frozen=True)
class ContextResolution:
    query: str
    used_context: bool
    source_turn_id: str | None = None


def looks_like_report_request(query: str) -> bool:
    normalized = query.strip(" ，,。；;？?")
    return any(phrase in normalized for phrase in REPORT_PHRASES)


def find_report_source_turn(
    turns: list[dict[str, Any]] | None,
    source_turn_id: str | None = None,
) -> dict[str, Any] | None:
    if not turns:
        return None
    return next(
        (
            turn
            for turn in reversed(turns)
            if turn.get("intent") in REPORT_SOURCE_INTENTS
            and isinstance(turn.get("sql_result"), dict)
            and (source_turn_id is None or turn.get("turn_id") == source_turn_id)
        ),
        None,
    )


def looks_like_contextual_followup(query: str) -> bool:
    normalized = query.strip(" ，,。；;？?")
    if not normalized or len(normalized) > 40:
        return False
    return (
        normalized.startswith(CONTEXT_PREFIXES)
        or (len(normalized) <= 8 and normalized.endswith("怎么样"))
        or (len(normalized) <= 8 and normalized.endswith("呢"))
    )


def resolve_contextual_query(
    query: str,
    turns: list[dict[str, Any]] | None,
) -> ContextResolution:
    cleaned = query.strip()
    if not turns or not looks_like_contextual_followup(cleaned):
        return ContextResolution(query=cleaned, used_context=False)

    previous_turn = next(
        (
            turn
            for turn in reversed(turns)
            if turn.get("intent") in ANALYTICAL_INTENTS
            and isinstance(turn.get("query"), str)
            and str(turn["query"]).strip()
        ),
        None,
    )
    if previous_turn is None:
        return ContextResolution(query=cleaned, used_context=False)

    previous_query = str(previous_turn["query"]).strip(" ，,。；;？?")
    resolved = f"{previous_query}；基于上一问题继续追问：{cleaned}"
    turn_id = previous_turn.get("turn_id")
    return ContextResolution(
        query=resolved,
        used_context=True,
        source_turn_id=str(turn_id) if turn_id is not None else None,
    )

"""Send a redacted privacy probe and optional live LLM span to LangSmith."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.graph.workflow import get_graph
from app.llm.deepseek import get_llm_client
from app.observability.langsmith import (
    get_langsmith_client,
    observe_chain,
    trace_agent_request,
)

PROBE_SESSION_ID = "langsmith-privacy-probe"
PROBE_SECRET = "probe-secret-must-not-leave-app"
SECRET_PATTERN = re.compile(
    r"(?i)(?:lsv2_[a-z0-9_\-]{16,}|sk-[a-z0-9_\-]{16,}|"
    r"mysql\+aiomysql://[^\s]+@)"
)


def _unsafe_rows(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "rows" and not (
                isinstance(item, dict) and item.get("omitted") is True
            ):
                return True
            if _unsafe_rows(item):
                return True
    elif isinstance(value, list):
        return any(_unsafe_rows(item) for item in value)
    return False


async def run_probe(*, live_llm: bool) -> None:
    settings = get_settings()
    if not settings.langsmith_enabled:
        raise SystemExit(
            "LangSmith is disabled. Configure LANGSMITH_TRACING=true and LANGSMITH_API_KEY."
        )

    started_at = datetime.now(UTC)
    llm_error: str | None = None
    base_config = {"configurable": {"thread_id": PROBE_SESSION_ID}}
    with trace_agent_request(
        session_id=PROBE_SESSION_ID,
        query="LangSmith privacy probe",
        config=base_config,
    ) as (traced_config, tracer):
        await get_graph().ainvoke(
            {
                "user_query": "介绍一下系统能力",
                "session_id": PROBE_SESSION_ID,
                "turns": [],
            },
            config=traced_config,
        )
        async with observe_chain(
            "langsmith.privacy_probe",
            inputs={
                "api_key": PROBE_SECRET,
                "database_url": "mysql+aiomysql://user:password@localhost/database",
                "sql_result": {
                    "columns": ["store_name", "sales"],
                    "rows": [{"store_name": "测试门店", "sales": 100}],
                    "row_count": 1,
                },
                "retrieved_docs": [{"content": "测试制度片段" * 200}],
            },
            tags=["langsmith", "privacy-probe"],
        ) as span:
            await span.end(
                {
                    "status": "ok",
                    "rows": [{"must": "not be uploaded"}],
                }
            )

        if live_llm:
            try:
                await get_llm_client().generate_text(
                    system="你是连通性检查助手。",
                    user="只回答：LangSmith追踪正常",
                    max_tokens=256,
                )
            except Exception as exc:
                llm_error = type(exc).__name__

    client = get_langsmith_client()
    if tracer is not None:
        tracer.wait_for_futures()
    client.flush()
    runs = []
    expected_names = {
        "retail-insight.request",
        "route",
        "general",
        "persist_turn",
        "langsmith.privacy_probe",
        "deepseek.generate_text",
    }
    relevant = []
    for _ in range(5):
        runs = list(
            client.list_runs(
                project_name=settings.langsmith_project,
                start_time=started_at,
                limit=50,
            )
        )
        relevant = [
            run
            for run in runs
            if run.name in expected_names
        ]
        if relevant:
            break
        await asyncio.sleep(1)
    serialized = json.dumps(
        [
            {
                "inputs": run.inputs,
                "outputs": run.outputs,
                "extra": run.extra,
            }
            for run in relevant
        ],
        ensure_ascii=False,
        default=str,
    )
    run_names = sorted({run.name for run in relevant})
    summary: dict[str, Any] = {
        "project": settings.langsmith_project,
        "trace_count": len(relevant),
        "run_names": run_names,
        "run_types": sorted({run.run_type for run in relevant}),
        "observed_run_names": sorted({run.name for run in runs}),
        "probe_secret_present": PROBE_SECRET in serialized,
        "secret_pattern_present": bool(SECRET_PATTERN.search(serialized)),
        "unsafe_rows_present": any(
            _unsafe_rows({"inputs": run.inputs, "outputs": run.outputs})
            for run in relevant
        ),
        "live_llm_error": llm_error,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not relevant:
        raise SystemExit("No validation trace was returned by LangSmith.")
    required_graph_runs = {
        "retail-insight.request",
        "route",
        "general",
        "persist_turn",
        "langsmith.privacy_probe",
    }
    missing_graph_runs = required_graph_runs - set(run_names)
    if missing_graph_runs:
        raise SystemExit(
            f"LangGraph validation trace is incomplete: {sorted(missing_graph_runs)}"
        )
    if summary["probe_secret_present"] or summary["secret_pattern_present"]:
        raise SystemExit("LangSmith privacy probe detected an unredacted secret.")
    if summary["unsafe_rows_present"]:
        raise SystemExit("LangSmith privacy probe detected raw database rows.")
    if live_llm and "deepseek.generate_text" not in run_names:
        raise SystemExit("The live DeepSeek LLM span was not returned by LangSmith.")
    if llm_error is not None:
        raise SystemExit(f"The live DeepSeek validation failed with {llm_error}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live-llm",
        action="store_true",
        help="also send one minimal request to the configured DeepSeek API",
    )
    arguments = parser.parse_args()
    asyncio.run(run_probe(live_llm=arguments.live_llm))

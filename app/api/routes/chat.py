import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest, ChatResponse
from app.graph.workflow import get_graph
from app.observability.langsmith import trace_agent_request

router = APIRouter(prefix="/chat", tags=["chat"])


def get_runtime_graph(request: Request) -> Any:
    return getattr(request.app.state, "graph", None) or get_graph()


def initial_state(request: ChatRequest) -> dict[str, Any]:
    return {
        "user_query": request.query,
        "resolved_query": None,
        "context_used": False,
        "context_source_turn_id": None,
        "session_id": request.session_id,
        "clarification": None,
        "selected_tables": [],
        "schema_context": "",
        "generated_sql": None,
        "sql_validation": None,
        "sql_result": None,
        "chart_spec": None,
        "answer": None,
        "retry_count": 0,
        "errors": [],
        "retrieved_docs": [],
        "citations": [],
        "tool_calls": [],
        "tool_results": [],
        "tool_round_count": 0,
        "report_artifact": None,
        "metrics": {},
    }


def response_from_state(request: ChatRequest, state: dict[str, Any]) -> ChatResponse:
    return ChatResponse(
        session_id=request.session_id,
        intent=state["intent"],
        resolved_query=state.get("resolved_query"),
        context_used=bool(state.get("context_used")),
        answer=state.get("answer") or "当前分支没有返回答案。",
        clarification=state.get("clarification"),
        generated_sql=state.get("generated_sql"),
        sql_result=state.get("sql_result"),
        chart_spec=state.get("chart_spec"),
        citations=state.get("citations", []),
        tool_calls=state.get("tool_calls", []),
        tool_results=state.get("tool_results", []),
        tool_round_count=state.get("tool_round_count", 0),
        report_artifact=state.get("report_artifact"),
        errors=state.get("errors", []),
        metrics=state.get("metrics", {}),
    )


def encode_sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    graph = get_runtime_graph(request)
    state = initial_state(payload)
    base_config = {"configurable": {"thread_id": payload.session_id}}
    with trace_agent_request(
        session_id=payload.session_id,
        query=payload.query,
        config=base_config,
    ) as (config, _):
        result = await graph.ainvoke(state, config=config)
    return response_from_state(payload, result)


@router.post("/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    graph = get_runtime_graph(request)
    config = {"configurable": {"thread_id": payload.session_id}}

    async def event_stream() -> AsyncIterator[str]:
        accumulated = initial_state(payload)
        yield encode_sse("start", {"session_id": payload.session_id})
        next_update: asyncio.Task[Any] | None = None
        with trace_agent_request(
            session_id=payload.session_id,
            query=payload.query,
            config=config,
        ) as (traced_config, _):
            iterator = graph.astream(
                accumulated,
                config=traced_config,
                stream_mode="updates",
            ).__aiter__()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    if next_update is None:
                        next_update = asyncio.create_task(anext(iterator))
                    done, _ = await asyncio.wait({next_update}, timeout=10)
                    if not done:
                        yield encode_sse("heartbeat", {"status": "running"})
                        continue
                    try:
                        update = next_update.result()
                    except StopAsyncIteration:
                        break
                    finally:
                        next_update = None

                    if not isinstance(update, dict):
                        continue
                    for node_name, node_update in update.items():
                        if isinstance(node_update, dict):
                            accumulated.update(node_update)
                        yield encode_sse("node", {"node": node_name})

                if "intent" not in accumulated:
                    raise RuntimeError("graph completed without an intent")
                response = response_from_state(payload, accumulated)
                yield encode_sse("result", response.model_dump(mode="json"))
                yield encode_sse("done", {"session_id": payload.session_id})
            except asyncio.CancelledError:
                if next_update is not None:
                    next_update.cancel()
                raise
            except Exception:
                if next_update is not None:
                    next_update.cancel()
                yield encode_sse("error", {"message": "请求处理失败，请稍后重试。"})
                yield encode_sse("done", {"session_id": payload.session_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request, status

from app.api.schemas import SessionDeleteResponse, SessionHistoryResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])

SESSION_ID = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")


def runtime_component(request: Request, name: str) -> Any:
    component = getattr(request.app.state, name, None)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="会话持久化服务尚未就绪。",
        )
    return component


@router.get("/{session_id}", response_model=SessionHistoryResponse)
async def get_session(
    request: Request,
    session_id: str = SESSION_ID,
) -> SessionHistoryResponse:
    graph = runtime_component(request, "graph")
    snapshot = await graph.aget_state(
        {"configurable": {"thread_id": session_id}},
    )
    values = snapshot.values if snapshot is not None else {}
    return SessionHistoryResponse(session_id=session_id, turns=values.get("turns", []))


@router.delete("/{session_id}", response_model=SessionDeleteResponse)
async def delete_session(
    request: Request,
    session_id: str = SESSION_ID,
) -> SessionDeleteResponse:
    checkpointer = runtime_component(request, "checkpointer")
    await checkpointer.adelete_thread(session_id)
    return SessionDeleteResponse(session_id=session_id, deleted=True)

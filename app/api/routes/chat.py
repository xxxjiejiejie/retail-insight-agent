from fastapi import APIRouter

from app.api.schemas import ChatRequest, ChatResponse
from app.graph.workflow import get_graph

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    graph = get_graph()
    initial_state = {
        "user_query": request.query,
        "session_id": request.session_id,
        "retry_count": 0,
        "errors": [],
        "retrieved_docs": [],
        "citations": [],
        "metrics": {},
    }
    result = await graph.ainvoke(
        initial_state,
        config={"configurable": {"thread_id": request.session_id}},
    )
    return ChatResponse(
        session_id=request.session_id,
        intent=result["intent"],
        answer=result.get("answer") or "当前分支没有返回答案。",
        clarification=result.get("clarification"),
        generated_sql=result.get("generated_sql"),
        sql_result=result.get("sql_result"),
        chart_spec=result.get("chart_spec"),
        citations=result.get("citations", []),
        metrics=result.get("metrics", {}),
    )

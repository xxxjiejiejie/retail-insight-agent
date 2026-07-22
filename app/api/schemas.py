from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.graph.state import Intent


class ChatRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    session_id: str = Field(default_factory=lambda: str(uuid4()))


class Citation(BaseModel):
    source: str
    section: str | None = None
    page: int | None = None
    excerpt: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    intent: Intent
    answer: str
    clarification: str | None = None
    generated_sql: str | None = None
    sql_result: dict[str, Any] | None = None
    chart_spec: dict[str, Any] | None = None
    citations: list[Citation] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


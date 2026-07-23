from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.graph.state import Intent


class ChatRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )


class Citation(BaseModel):
    source: str
    section: str | None = None
    page: int | None = None
    excerpt: str | None = None
    document_id: str | None = None
    version: str | None = None
    paragraph_id: str | None = None
    chunk_id: str | None = None
    relevance_score: float | None = None


class ChatMetrics(BaseModel):
    attempt_count: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    llm_latency_ms: float | None = None
    sql_execution_ms: float | None = None
    total_latency_ms: float | None = None
    sql_branch_ms: float | None = None
    rag_branch_ms: float | None = None
    hybrid_branch_ms: float | None = None
    retrieval_ms: float | None = None
    rerank_ms: float | None = None
    retrieved_count: int | None = None
    reranked_count: int | None = None
    evidence_count: int | None = None
    citation_count: int | None = None
    context_used: bool | None = None


class ChatResponse(BaseModel):
    session_id: str
    intent: Intent
    resolved_query: str | None = None
    context_used: bool = False
    answer: str
    clarification: str | None = None
    generated_sql: str | None = None
    sql_result: dict[str, Any] | None = None
    chart_spec: dict[str, Any] | None = None
    citations: list[Citation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: ChatMetrics = Field(default_factory=ChatMetrics)


class ChatTurn(BaseModel):
    turn_id: str
    created_at: datetime
    query: str
    resolved_query: str | None = None
    context_used: bool = False
    intent: Intent
    answer: str
    clarification: str | None = None
    generated_sql: str | None = None
    sql_result: dict[str, Any] | None = None
    chart_spec: dict[str, Any] | None = None
    citations: list[Citation] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: ChatMetrics = Field(default_factory=ChatMetrics)


class SessionHistoryResponse(BaseModel):
    session_id: str
    turns: list[ChatTurn] = Field(default_factory=list)


class SessionDeleteResponse(BaseModel):
    session_id: str
    deleted: bool


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str


class SchemaColumnResponse(BaseModel):
    name: str
    type: str
    nullable: bool


class SchemaTableResponse(BaseModel):
    name: str
    columns: list[SchemaColumnResponse]


class SchemaMetadataResponse(BaseModel):
    tables: list[SchemaTableResponse]


class PolicyMetadataItem(BaseModel):
    document_id: str
    title: str
    version: str
    effective_date: str
    source: str
    section_count: int
    chunk_count: int


class PolicyMetadataResponse(BaseModel):
    documents: list[PolicyMetadataItem]

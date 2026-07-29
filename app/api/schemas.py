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
    tool_round_count: int | None = None
    tool_call_count: int | None = None
    tool_latency_ms: float | None = None


class ToolCallTrace(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_summary: dict[str, Any] = Field(default_factory=dict)


class ToolResultTrace(BaseModel):
    tool_name: str
    arguments_summary: dict[str, Any] = Field(default_factory=dict)
    status: str
    latency_ms: float
    error_type: str | None = None
    result_count: int | None = None


class ReportArtifactResponse(BaseModel):
    report_id: str
    title: str
    format: str
    download_url: str
    source_turn_id: str
    created_at: datetime


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
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    tool_results: list[ToolResultTrace] = Field(default_factory=list)
    tool_round_count: int = 0
    report_artifact: ReportArtifactResponse | None = None
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
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    tool_results: list[ToolResultTrace] = Field(default_factory=list)
    tool_round_count: int = 0
    report_artifact: ReportArtifactResponse | None = None
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


class PolicySectionResponse(BaseModel):
    title: str
    content: str
    page: int | None = None


class PolicyDetailResponse(BaseModel):
    document_id: str
    title: str
    version: str
    effective_date: str
    source: str
    sections: list[PolicySectionResponse]


class EvaluationBranchMetricsResponse(BaseModel):
    passed: int
    total: int
    accuracy: float
    rejected: int
    rejection_rate: float
    total_tokens: int
    avg_tokens: float
    p50_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    coverage: str


class EvaluationQualityGateResponse(BaseModel):
    passed: int
    total: int
    accuracy: float
    duration_ms: float | None = None
    categories: dict[str, Any] = Field(default_factory=dict)


class EvaluationSetMetricsResponse(BaseModel):
    passed: int
    total: int
    accuracy: float
    categories: dict[str, Any] = Field(default_factory=dict)
    description: str


class EvaluationKnownLimitationResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str


class EvaluationImprovementResponse(BaseModel):
    id: str
    title: str
    problem: str
    change: str
    evidence: str
    status: str


class EvaluationFailureResponse(BaseModel):
    case_id: str
    branch: str
    set_type: str = "normal"
    failure_type: str
    diagnosis: str
    question: str
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    generated_sql: str | None = None
    total_tokens: float | None = None
    latency_ms: float | None = None


class RAGAblationPipelineMetricsResponse(BaseModel):
    label: str
    hit_at_5: float
    mrr_at_5: float
    ndcg_at_5: float
    p50_latency_ms: float
    p95_latency_ms: float
    evaluated_answerable_cases: int
    failure_count: int
    negative_nonempty_rate: float
    negative_mean_top_score: float


class RAGAblationCorpusResponse(BaseModel):
    document_count: int
    chunk_count: int
    domain_count: int
    corpus_version: str


class RAGAblationFailureResponse(BaseModel):
    pipeline: str
    case_id: str
    split: str
    category: str
    question: str
    expected_document_ids: list[str] = Field(default_factory=list)
    retrieved_document_ids: list[str] = Field(default_factory=list)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)


class RAGAblationResponse(BaseModel):
    generated_at: datetime
    dataset_version: str
    top_k: int
    total_cases: int
    answerable_cases: int
    negative_cases: int
    corpus: RAGAblationCorpusResponse
    pipelines: dict[str, RAGAblationPipelineMetricsResponse]
    negative_summary: dict[str, Any] = Field(default_factory=dict)
    failures: list[RAGAblationFailureResponse] = Field(default_factory=list)


class EvaluationRunSummaryResponse(BaseModel):
    run_id: str
    label: str
    generated_at: datetime
    model: str
    dataset_version: str
    git_commit: str | None = None
    workspace_state: str
    total_cases: int
    total_passed: int
    overall_accuracy: float
    failure_count: int = 0
    branches: dict[str, EvaluationBranchMetricsResponse]
    evaluation_sets: dict[str, EvaluationSetMetricsResponse] = Field(default_factory=dict)
    known_limitations: list[EvaluationKnownLimitationResponse] = Field(default_factory=list)
    improvements: list[EvaluationImprovementResponse] = Field(default_factory=list)
    quality_gate: EvaluationQualityGateResponse | None = None


class EvaluationRunResponse(EvaluationRunSummaryResponse):
    failures: list[EvaluationFailureResponse] = Field(default_factory=list)
    rag_ablation: RAGAblationResponse | None = None
    source_reports: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvaluationRunListResponse(BaseModel):
    runs: list[EvaluationRunSummaryResponse] = Field(default_factory=list)

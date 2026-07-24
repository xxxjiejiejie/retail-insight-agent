export type Intent = "sql" | "rag" | "hybrid" | "clarify" | "general"

export interface Citation {
  source: string
  section?: string | null
  page?: number | null
  excerpt?: string | null
  document_id?: string | null
  version?: string | null
  paragraph_id?: string | null
  chunk_id?: string | null
  relevance_score?: number | null
}

export interface ChartSpec {
  type: "bar" | "line" | "pie" | "scatter"
  title: string
  x_field: string
  y_field: string
}

export interface SQLResult {
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  execution_ms: number
  executed_sql: string
  history_truncated?: boolean
}

export interface ChatMetrics {
  attempt_count?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  llm_latency_ms?: number
  sql_execution_ms?: number
  total_latency_ms?: number
  sql_branch_ms?: number
  rag_branch_ms?: number
  hybrid_branch_ms?: number
  retrieval_ms?: number
  rerank_ms?: number
  retrieved_count?: number
  reranked_count?: number
  evidence_count?: number
  citation_count?: number
  context_used?: boolean
}

export interface ChatResponse {
  session_id: string
  intent: Intent
  resolved_query?: string | null
  context_used: boolean
  answer: string
  clarification?: string | null
  generated_sql?: string | null
  sql_result?: SQLResult | null
  chart_spec?: ChartSpec | null
  citations: Citation[]
  errors: string[]
  metrics: ChatMetrics
}

export interface ChatTurn {
  turn_id: string
  created_at: string
  query: string
  resolved_query?: string | null
  context_used: boolean
  intent: Intent
  answer: string
  clarification?: string | null
  generated_sql?: string | null
  sql_result?: SQLResult | null
  chart_spec?: ChartSpec | null
  citations: Citation[]
  errors: string[]
  metrics: ChatMetrics
}

export interface SessionHistoryResponse {
  session_id: string
  turns: ChatTurn[]
}

export interface SessionDeleteResponse {
  session_id: string
  deleted: boolean
}

export interface SchemaColumn {
  name: string
  type: string
  nullable: boolean
}

export interface SchemaTable {
  name: string
  columns: SchemaColumn[]
}

export interface SchemaMetadataResponse {
  tables: SchemaTable[]
}

export interface PolicyMetadataItem {
  document_id: string
  title: string
  version: string
  effective_date: string
  source: string
  section_count: number
  chunk_count: number
}

export interface PolicyMetadataResponse {
  documents: PolicyMetadataItem[]
}

export interface PolicySection {
  title: string
  content: string
  page?: number | null
}

export interface PolicyDetailResponse {
  document_id: string
  title: string
  version: string
  effective_date: string
  source: string
  sections: PolicySection[]
}

export interface HealthResponse {
  status: string
  app: string
  environment: string
}

export type EvaluationBranch = "sql" | "rag" | "hybrid"

export interface EvaluationBranchMetrics {
  passed: number
  total: number
  accuracy: number
  rejected: number
  rejection_rate: number
  total_tokens: number
  avg_tokens: number
  p50_latency_ms?: number | null
  p95_latency_ms?: number | null
  coverage: string
}

export interface EvaluationQualityGate {
  passed: number
  total: number
  accuracy: number
  duration_ms?: number | null
  categories: Record<string, { passed: number; total: number; pass_rate: number }>
}

export interface EvaluationSetMetrics {
  passed: number
  total: number
  accuracy: number
  categories: Record<string, { passed: number; total: number; accuracy: number }>
  description: string
}

export interface EvaluationKnownLimitation {
  id: string
  title: string
  description: string
  status: string
}

export interface EvaluationFailure {
  case_id: string
  branch: EvaluationBranch
  set_type: "normal" | "challenge"
  failure_type: string
  diagnosis: string
  question: string
  expected: Record<string, unknown>
  actual: Record<string, unknown>
  errors: string[]
  generated_sql?: string | null
  total_tokens?: number | null
  latency_ms?: number | null
}

export interface EvaluationRunSummary {
  run_id: string
  label: string
  generated_at: string
  model: string
  dataset_version: string
  git_commit?: string | null
  workspace_state: string
  total_cases: number
  total_passed: number
  overall_accuracy: number
  branches: Record<EvaluationBranch, EvaluationBranchMetrics>
  evaluation_sets?: Record<string, EvaluationSetMetrics>
  known_limitations?: EvaluationKnownLimitation[]
  quality_gate?: EvaluationQualityGate | null
}

export interface EvaluationRun extends EvaluationRunSummary {
  failures: EvaluationFailure[]
  source_reports: string[]
  notes: string[]
}

export interface EvaluationRunListResponse {
  runs: EvaluationRunSummary[]
}

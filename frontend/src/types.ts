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

export interface HealthResponse {
  status: string
  app: string
  environment: string
}

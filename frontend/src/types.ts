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
}

export interface ChatResponse {
  session_id: string
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

export interface ChatTurn {
  turn_id: string
  created_at: string
  query: string
  intent: Intent
  answer: string
  generated_sql?: string | null
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

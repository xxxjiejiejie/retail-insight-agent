export type Intent = "sql" | "rag" | "hybrid" | "clarify" | "general"

export interface Citation {
  source: string
  section?: string | null
  page?: number | null
  excerpt?: string | null
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

export interface ChatResponse {
  session_id: string
  intent: Intent
  answer: string
  clarification?: string | null
  generated_sql?: string | null
  sql_result?: SQLResult | null
  chart_spec?: ChartSpec | null
  citations: Citation[]
  metrics: Record<string, unknown>
}

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

export interface ChatResponse {
  session_id: string
  intent: Intent
  answer: string
  clarification?: string | null
  generated_sql?: string | null
  sql_result?: Record<string, unknown> | null
  chart_spec?: ChartSpec | null
  citations: Citation[]
  metrics: Record<string, unknown>
}


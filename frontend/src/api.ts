import axios from "axios"

import type {
  ChatResponse,
  EvaluationRun,
  EvaluationRunListResponse,
  HealthResponse,
  PolicyDetailResponse,
  PolicyMetadataResponse,
  SessionDeleteResponse,
  SessionHistoryResponse,
  SchemaMetadataResponse,
} from "./types"

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api/v1"
const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30_000,
})

export type StreamEventHandler = (event: string, data: Record<string, unknown>) => void

function parseEventBlock(
  block: string,
  onEvent: StreamEventHandler,
): { result?: ChatResponse; error?: string } {
  let event = "message"
  const dataLines: string[] = []
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim()
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return {}

  const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>
  onEvent(event, data)
  if (event === "result") return { result: data as unknown as ChatResponse }
  if (event === "error") return { error: String(data.message || "请求处理失败，请稍后重试。") }
  return {}
}

export async function streamQuestion(
  query: string,
  sessionId: string,
  onEvent: StreamEventHandler,
): Promise<ChatResponse> {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 180_000)
  let finalResult: ChatResponse | undefined
  let buffer = ""

  try {
    const response = await fetch(`${apiBaseUrl}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: sessionId }),
      signal: controller.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(`请求失败（HTTP ${response.status}）`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n")
      const blocks = buffer.split("\n\n")
      buffer = blocks.pop() || ""
      for (const block of blocks) {
        const parsed = parseEventBlock(block, onEvent)
        if (parsed.error) throw new Error(parsed.error)
        if (parsed.result) finalResult = parsed.result
      }
      if (done) break
    }
    if (buffer.trim()) {
      const parsed = parseEventBlock(buffer, onEvent)
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.result) finalResult = parsed.result
    }
  } finally {
    window.clearTimeout(timeoutId)
  }

  if (!finalResult) throw new Error("流式响应结束，但没有收到最终结果。")
  return finalResult
}

export async function getSessionHistory(sessionId: string): Promise<SessionHistoryResponse> {
  const response = await api.get<SessionHistoryResponse>(`/sessions/${sessionId}`)
  return response.data
}

export async function deleteSession(sessionId: string): Promise<SessionDeleteResponse> {
  const response = await api.delete<SessionDeleteResponse>(`/sessions/${sessionId}`)
  return response.data
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await api.get<HealthResponse>("/health")
  return response.data
}

export async function getSchemaMetadata(): Promise<SchemaMetadataResponse> {
  const response = await api.get<SchemaMetadataResponse>("/metadata/schema")
  return response.data
}

export async function getPolicyMetadata(): Promise<PolicyMetadataResponse> {
  const response = await api.get<PolicyMetadataResponse>("/metadata/policies")
  return response.data
}

export async function getPolicyDetail(documentId: string): Promise<PolicyDetailResponse> {
  const response = await api.get<PolicyDetailResponse>(
    `/metadata/policies/${encodeURIComponent(documentId)}`,
  )
  return response.data
}

export async function getEvaluationRuns(): Promise<EvaluationRunListResponse> {
  const response = await api.get<EvaluationRunListResponse>("/evaluation/runs")
  return response.data
}

export async function getEvaluationRun(runId: string): Promise<EvaluationRun> {
  const response = await api.get<EvaluationRun>(
    `/evaluation/runs/${encodeURIComponent(runId)}`,
  )
  return response.data
}

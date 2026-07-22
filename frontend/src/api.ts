import axios from "axios"

import type { ChatResponse } from "./types"

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api/v1",
  timeout: 30_000,
})

export async function sendQuestion(query: string, sessionId: string): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>("/chat", {
    query,
    session_id: sessionId,
  })
  return response.data
}


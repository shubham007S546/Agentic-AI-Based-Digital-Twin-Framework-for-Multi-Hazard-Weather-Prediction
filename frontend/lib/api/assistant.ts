import { apiFetch } from '@/lib/api/client'

export interface AssistantQueryResponse {
  question: string
  rewritten_question?: string
  answer: string
  sources: string[]
  retrieval?: unknown
}

interface AssistantApiResponse {
  success: boolean
  data: AssistantQueryResponse
  message: string
  request_id?: string
  timestamp: string
}

export async function askAssistant(question: string): Promise<AssistantQueryResponse> {
  const response = await apiFetch<AssistantApiResponse>('/agents/assistant/query', {
    method: 'POST',
    body: JSON.stringify({ question }),
  })

  return response.data
}

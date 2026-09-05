import { apiFetch } from '@/lib/api/client'

export interface AgentHealth {
  agent_name: string
  version: string
  is_healthy: boolean
  last_execution_status: string | null
  last_execution_at: string | null
}

export interface RagHealth {
  ready: boolean
  index_path: string
  document_count: number
  vector_count: number
  reason?: string
}

export async function getAgentHealth(): Promise<AgentHealth[]> {
  const response = await apiFetch<{ data: AgentHealth[] }>('/agents/health', {
    cache: 'no-store',
  })
  return response.data
}

export async function getRagHealth(): Promise<RagHealth> {
  const response = await apiFetch<{ data: RagHealth }>('/agents/rag/health', {
    cache: 'no-store',
  })
  return response.data
}

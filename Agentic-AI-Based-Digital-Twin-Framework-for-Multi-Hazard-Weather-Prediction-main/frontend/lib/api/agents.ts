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

export interface PromptSpecification {
  agent_name: string
  role_description: string
  system_prompt: string
  expected_answer_schema: Record<string, string>
  constraints: string[]
}

export interface AgentExecutionReport {
  agent_name: string
  agent_role: string
  execution_id: string
  timestamp: string
  duration_ms: number
  status: string
  task_assigned: Record<string, any>
  actions_taken: string[]
  prompt_specification?: PromptSpecification
  final_answer: Record<string, any>
  summary_markdown: string
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

export async function getAgentPrompts(): Promise<Record<string, PromptSpecification>> {
  const response = await apiFetch<{ data: Record<string, PromptSpecification> }>('/agents/prompts', {
    cache: 'no-store',
  })
  return response.data
}

export async function runAgentSync(
  agentName: string,
  payload?: Record<string, any>
): Promise<{
  agent: string
  status: string
  duration_seconds: number
  result_summary: Record<string, any>
  agent_report?: AgentExecutionReport
  final_answer?: Record<string, any>
}> {
  const response = await apiFetch<{ data: any }>(`/agents/${agentName}/run`, {
    method: 'POST',
    body: JSON.stringify(payload || {}),
    cache: 'no-store',
  })
  return response.data
}

export async function queryOrchestrator(
  query: string,
  context?: Record<string, any>
): Promise<{
  session_id: string
  response: string
  intent: Record<string, any>
  tools_used: any[]
  agent_reports: Record<string, AgentExecutionReport>
  notifications: any[]
  errors: string[]
}> {
  const response = await apiFetch<{ data: any }>('/agents/orchestrator/query', {
    method: 'POST',
    body: JSON.stringify({ query, context: context || {}, session_id: 'web-session' }),
    cache: 'no-store',
  })
  return response.data
}

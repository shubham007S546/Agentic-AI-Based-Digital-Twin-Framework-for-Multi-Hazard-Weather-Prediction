/**
 * lib/api/orchestrator.ts
 * Frontend client for the Orchestrator Agent proxy endpoint.
 * All natural-language multi-agent queries go through here.
 */

import { apiFetch, fetchWithFallback } from './client'

// ── Types ────────────────────────────────────────────────────────────────────

export interface OrchestratorRequest {
  query: string
  session_id?: string
  context?: Record<string, unknown>
}

export interface ToolCallRecord {
  tool: string
  params: Record<string, unknown>
  result_summary: string
  duration_ms: number
  success: boolean
}

export interface OrchestratorResponse {
  session_id: string
  response: string
  intent: {
    intent_type: string
    location: string
    hazard: string
    time_horizon: string
    confidence: number
  }
  tools_used: ToolCallRecord[]
  notifications: string[]
  errors: string[]
}

// ── Mock fallback ─────────────────────────────────────────────────────────────

const MOCK_RESPONSE: OrchestratorResponse = {
  session_id: 'demo',
  response:
    'Based on current meteorological data, Mandi district faces a HIGH flood risk over the next 24 hours. ' +
    'Expected rainfall of 85–110 mm combined with saturated soils and elevated Beas river levels suggests ' +
    'peak discharge near 620 m³/s. I recommend immediate pre-positioning of NDRF teams and issuing Orange Alert.',
  intent: {
    intent_type: 'flood_risk_query',
    location: 'Mandi',
    hazard: 'flood',
    time_horizon: '24h',
    confidence: 0.91,
  },
  tools_used: [
    {
      tool: 'weather_tool',
      params: { location: 'Mandi', hours: 24 },
      result_summary: 'Forecast: 92mm expected, 88% probability heavy rain',
      duration_ms: 340,
      success: true,
    },
    {
      tool: 'prediction_tool',
      params: { hazard: 'flood', location: 'Mandi' },
      result_summary: 'Flood probability: 0.78, peak discharge 620 m³/s',
      duration_ms: 820,
      success: true,
    },
    {
      tool: 'alert_tool',
      params: { location: 'Mandi' },
      result_summary: 'Current alert level: Orange',
      duration_ms: 210,
      success: true,
    },
  ],
  notifications: [],
  errors: [],
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Send a natural-language query to the Orchestrator Agent via backend proxy */
export async function queryOrchestrator(
  req: OrchestratorRequest,
): Promise<OrchestratorResponse> {
  return fetchWithFallback(
    () =>
      apiFetch<{ data: OrchestratorResponse }>('/agents/orchestrator/query', {
        method: 'POST',
        body: JSON.stringify({
          query: req.query,
          session_id: req.session_id ?? 'default',
          context: req.context ?? {},
        }),
      }).then((r) => r.data),
    MOCK_RESPONSE,
  )
}

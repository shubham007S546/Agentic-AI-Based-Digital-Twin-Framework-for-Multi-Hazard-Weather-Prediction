/**
 * lib/api/twin.ts
 * Digital Twin API — talks to the backend's /api/v1/twin endpoints,
 * which delegate to the standalone Digital Twin Agent on port 8004.
 */

import { apiFetch, fetchWithFallback } from './client'

// ── Types ────────────────────────────────────────────────────────────────────

export interface TwinStateResponse {
  district: string
  timestamp: string
  weather_state: Record<string, unknown>
  hydrological_state: Record<string, unknown>
  geological_state: Record<string, unknown>
  infrastructure_state: Record<string, unknown>
  is_latest: boolean
}

export interface SimulationRequest {
  district: string
  scenario: string
  /** e.g. { "precipitation_multiplier": 2.5 } */
  parameters: Record<string, number | string>
}

export interface SimulationResult {
  simulation_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  district: string
  scenario: string
  results?: {
    flood_severity: string
    peak_discharge_m3s: number
    flood_depth_m: number
    landslide_probability: number
    infrastructure_impact: string[]
    population_at_risk: number
    recommended_actions: string[]
  }
  error_message?: string
}

// ── Mock fallback data ────────────────────────────────────────────────────────

const MOCK_TWIN_STATE: TwinStateResponse = {
  district: 'MANDI',
  timestamp: new Date().toISOString(),
  weather_state: { rainfall_mm: 24.6, temperature_c: 18.4, humidity_pct: 82 },
  hydrological_state: {
    river_level_m: 4.2,
    danger_level_m: 6.0,
    peak_discharge_m3s: 312,
    flood_severity: 'moderate',
  },
  geological_state: {
    landslide_probability: 0.34,
    slope_stability: 'marginal',
    soil_saturation_pct: 71,
  },
  infrastructure_state: {
    roads_affected: ['NH-3 km 48-52'],
    bridges_at_risk: ['Pandoh Bridge'],
    power_outages: 0,
  },
  is_latest: true,
}

const MOCK_SIMULATION: SimulationResult = {
  simulation_id: 'sim-mock-001',
  status: 'completed',
  district: 'MANDI',
  scenario: 'heavy-rain',
  results: {
    flood_severity: 'high',
    peak_discharge_m3s: 748,
    flood_depth_m: 2.1,
    landslide_probability: 0.67,
    infrastructure_impact: ['NH-3 km 44-60', 'Pandoh Bridge', 'Mandi town road'],
    population_at_risk: 12400,
    recommended_actions: [
      'Issue Red Alert for Mandi district',
      'Pre-position NDRF teams at Pandoh',
      'Evacuate low-lying areas within 500m of Beas river',
    ],
  },
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Get the latest twin state for a district */
export async function getTwinState(district: string): Promise<TwinStateResponse> {
  return fetchWithFallback(
    () => apiFetch<TwinStateResponse>(`/twin/state/${district}`),
    MOCK_TWIN_STATE,
  )
}

/** Run a what-if simulation via the Digital Twin Agent */
export async function runSimulation(req: SimulationRequest): Promise<SimulationResult> {
  return fetchWithFallback(
    () =>
      apiFetch<SimulationResult>('/twin/simulate', {
        method: 'POST',
        body: JSON.stringify(req),
      }),
    MOCK_SIMULATION,
  )
}

/** Poll simulation status by ID */
export async function getSimulationStatus(simulationId: string): Promise<SimulationResult> {
  return fetchWithFallback(
    () => apiFetch<SimulationResult>(`/twin/simulate/${simulationId}`),
    MOCK_SIMULATION,
  )
}

/**
 * lib/api/predictions.ts
 * Hazard prediction API calls with mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import { FORECAST_7D, HAZARD_STATIONS } from '@/lib/mock/data'

export interface HazardPrediction {
  hazard: 'flood' | 'cloudburst' | 'rainfall'
  district: string
  probability: number
  risk: 'low' | 'moderate' | 'high' | 'severe'
  confidence: number
  horizon_hours: number
  predicted_at: string
}

interface PredictionsResponse {
  data: HazardPrediction[]
}

const MOCK_PREDICTIONS: HazardPrediction[] = HAZARD_STATIONS.map((st) => ({
  hazard: 'flood' as const,
  district: st.district,
  probability: st.probability,
  risk: st.risk,
  confidence: 87,
  horizon_hours: 24,
  predicted_at: new Date().toISOString(),
}))

export async function getFloodPredictions(): Promise<HazardPrediction[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<PredictionsResponse>('/predictions/flood')
      return res.data
    },
    MOCK_PREDICTIONS.filter((p) => p.hazard === 'flood'),
  )
}

export async function getCloudburstPredictions(): Promise<HazardPrediction[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<PredictionsResponse>('/predictions/cloudburst')
      return res.data
    },
    MOCK_PREDICTIONS.map((p) => ({ ...p, hazard: 'cloudburst' as const })),
  )
}

export async function getRainfallForecast(): Promise<typeof FORECAST_7D> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<{ data: typeof FORECAST_7D }>('/predictions/rainfall/forecast')
      return res.data
    },
    FORECAST_7D,
  )
}

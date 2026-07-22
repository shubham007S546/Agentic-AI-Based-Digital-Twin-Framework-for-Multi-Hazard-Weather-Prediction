/**
 * lib/api/predictions.ts
 * Multi-hazard prediction API calls with live backend integration and mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import { FORECAST_7D, HAZARD_STATIONS } from '@/lib/mock/data'
import type { RiskLevel } from '@/types'

export interface HazardPrediction {
  hazard: 'flood' | 'cloudburst' | 'rainfall' | 'landslide'
  district: string
  probability: number
  risk: RiskLevel
  confidence: number
  horizon_hours: number
  predicted_at?: string
  predicted_rainfall_mm?: number
  model?: string
}

export interface LandslideZone {
  zone: string
  corridor: string
  district: string
  susceptibility: number
  saturation: number
  risk: RiskLevel
}

export interface LandslidePredictionsResponse {
  data: HazardPrediction[]
  slope_zones: LandslideZone[]
  summary: {
    zones_monitored: number
    critical_zones: number
    corridors_at_risk: number
  }
}

interface PredictionsResponse {
  data: HazardPrediction[]
}

const MOCK_PREDICTIONS: HazardPrediction[] = HAZARD_STATIONS.map((st) => ({
  hazard: 'rainfall' as const,
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
    MOCK_PREDICTIONS.map((p) => ({ ...p, hazard: 'flood' as const })),
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

export async function getRainfallPredictions(): Promise<HazardPrediction[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<PredictionsResponse>('/predictions/rainfall')
      return res.data
    },
    MOCK_PREDICTIONS.map((p) => ({ ...p, hazard: 'rainfall' as const })),
  )
}

export async function getLandslidePredictions(): Promise<LandslidePredictionsResponse> {
  const fallbackZones: LandslideZone[] = [
    { zone: 'Hanogi (NH-3)', corridor: 'Mandi–Kullu', district: 'Mandi', susceptibility: 0.88, saturation: 94, risk: 'severe' },
    { zone: 'Kotrupi', corridor: 'Mandi–Pathankot', district: 'Mandi', susceptibility: 0.81, saturation: 90, risk: 'severe' },
    { zone: 'Nigulsari (NH-5)', corridor: 'Rampur–Kinnaur', district: 'Shimla', susceptibility: 0.72, saturation: 82, risk: 'high' },
    { zone: 'Banala', corridor: 'Kullu–Manali', district: 'Kullu', susceptibility: 0.64, saturation: 78, risk: 'high' },
    { zone: 'Chamba bypass', corridor: 'Chamba–Bharmour', district: 'Chamba', susceptibility: 0.48, saturation: 65, risk: 'moderate' },
    { zone: 'Solan section', corridor: 'Kalka–Shimla', district: 'Shimla', susceptibility: 0.31, saturation: 52, risk: 'low' },
  ]

  return fetchWithFallback(
    async () => {
      const res = await apiFetch<LandslidePredictionsResponse>('/predictions/landslide')
      return res
    },
    {
      data: MOCK_PREDICTIONS.map((p) => ({ ...p, hazard: 'landslide' as const })),
      slope_zones: fallbackZones,
      summary: {
        zones_monitored: 142,
        critical_zones: 2,
        corridors_at_risk: 4,
      },
    },
  )
}

export async function getRainfallForecast(district: string = 'Mandi'): Promise<typeof FORECAST_7D> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<{ data: typeof FORECAST_7D }>(`/predictions/rainfall/forecast?district=${district}`)
      return res.data
    },
    FORECAST_7D,
  )
}
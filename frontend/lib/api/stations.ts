/**
 * lib/api/stations.ts
 * Hazard station data API calls with mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import { HAZARD_STATIONS } from '@/lib/mock/data'
import type { HazardStation } from '@/types'

interface StationsResponse {
  data: HazardStation[]
}
interface StationResponse {
  data: HazardStation
}

export async function getHazardStations(): Promise<HazardStation[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<StationsResponse>('/weather/stations')
      return res.data
    },
    HAZARD_STATIONS,
  )
}

export async function getStationDetail(id: string): Promise<HazardStation | null> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<StationResponse>(`/weather/stations/${id}`)
      return res.data
    },
    HAZARD_STATIONS.find((s) => s.id === id) ?? null,
  )
}

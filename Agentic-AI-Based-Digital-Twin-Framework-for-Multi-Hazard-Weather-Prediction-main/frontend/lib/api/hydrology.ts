/**
 * lib/api/hydrology.ts
 * River gauge and hydrology data API calls with mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import { RIVER_GAUGES } from '@/lib/mock/data'
import type { RiverGauge } from '@/types'

interface GaugesResponse {
  data: RiverGauge[]
}

export async function getRiverGauges(): Promise<RiverGauge[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<GaugesResponse>('/weather/hydrology/gauges')
      return res.data
    },
    RIVER_GAUGES,
  )
}

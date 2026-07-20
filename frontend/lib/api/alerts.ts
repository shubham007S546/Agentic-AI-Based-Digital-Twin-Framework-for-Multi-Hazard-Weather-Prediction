/**
 * lib/api/alerts.ts
 * Alert data API calls with mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import { ALERTS } from '@/lib/mock/data'
import type { AlertItem } from '@/types'

interface AlertsResponse {
  data: AlertItem[]
  total: number
}

export async function getActiveAlerts(limit = 20): Promise<AlertItem[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<AlertsResponse>(`/alerts?limit=${limit}&status=active`)
      return res.data
    },
    ALERTS,
  )
}

export async function getAllAlerts(limit = 50, offset = 0): Promise<{ data: AlertItem[]; total: number }> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<AlertsResponse>(`/alerts?limit=${limit}&offset=${offset}`)
      return res
    },
    { data: ALERTS, total: ALERTS.length },
  )
}

'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { CloudRain, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import type { HazardPrediction } from '@/lib/api/predictions'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type HazardType = 'flood' | 'cloudburst' | 'rainfall' | 'landslide'

interface LiveDistrictRiskProps {
  hazard: HazardType
  initialData: HazardPrediction[]
  /** Auto-refresh interval in ms. Default 5 minutes. 0 = disabled. */
  refreshIntervalMs?: number
}

// ---------------------------------------------------------------------------
// Internal client-side fetcher — no function props crossing the server/client boundary
// ---------------------------------------------------------------------------

const BASE_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
  'http://localhost:8000/api/v1'

async function fetchPredictions(hazard: HazardType): Promise<HazardPrediction[]> {
  const endpoint = `${BASE_URL}/predictions/${hazard}`
  const res = await fetch(endpoint, { cache: 'no-store' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  // Backend wraps in { data: [...] }
  const items: unknown[] = Array.isArray(json?.data) ? json.data : Array.isArray(json) ? json : []
  return items as HazardPrediction[]
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------

const TITLE_MAP: Record<HazardType, string> = {
  flood: 'District Flood Risk',
  cloudburst: 'District Cloudburst Risk',
  rainfall: 'District Rainfall Nowcast & Risk',
  landslide: 'District Landslide Risk',
}

const HAZARD_ICON_CLASS: Record<HazardType, string> = {
  flood: 'text-blue-400',
  cloudburst: 'text-yellow-400',
  rainfall: 'text-primary',
  landslide: 'text-orange-400',
}

function probabilityBarClass(prob: number): string {
  if (prob > 60) return 'h-full bg-destructive'
  if (prob > 30) return 'h-full bg-warning'
  return 'h-full bg-primary'
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LiveDistrictRisk({
  hazard,
  initialData,
  refreshIntervalMs = 5 * 60 * 1000,
}: LiveDistrictRiskProps) {
  const [predictions, setPredictions] = useState<HazardPrediction[]>(initialData)
  const [isLoading, setIsLoading] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())
  const [error, setError] = useState<string | null>(null)
  const [isOnline, setIsOnline] = useState(true)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  // Keep initialData in sync if parent re-renders with fresh SSR data
  useEffect(() => {
    if (initialData?.length) {
      setPredictions(initialData)
    }
  }, [initialData])

  const refresh = useCallback(async () => {
    if (!mountedRef.current) return
    setIsLoading(true)
    setError(null)
    try {
      const fresh = await fetchPredictions(hazard)
      if (!mountedRef.current) return
      if (fresh.length > 0) {
        setPredictions(fresh)
        setIsOnline(true)
      }
      setLastUpdated(new Date())
    } catch (e) {
      if (!mountedRef.current) return
      setIsOnline(false)
      setError('Backend unreachable — showing last known values.')
    } finally {
      if (mountedRef.current) setIsLoading(false)
    }
  }, [hazard])

  // Auto-refresh timer
  useEffect(() => {
    if (!refreshIntervalMs) return
    const id = setInterval(refresh, refreshIntervalMs)
    return () => clearInterval(id)
  }, [refresh, refreshIntervalMs])

  const iconClass = HAZARD_ICON_CLASS[hazard] ?? 'text-primary'
  const title = TITLE_MAP[hazard] ?? 'District Risk'
  const modelLabel = predictions[0]?.model ?? 'lstm_v1_live'

  return (
    <GlassCard className="p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-medium">{title} — Live</h2>
          {isOnline ? (
            <Wifi className="size-3.5 text-success" aria-label="Backend connected" />
          ) : (
            <WifiOff className="size-3.5 text-muted-foreground" aria-label="Using cached data" />
          )}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-muted-foreground">
            model: {modelLabel} · {lastUpdated.toLocaleTimeString()}
          </span>
          <button
            type="button"
            onClick={refresh}
            disabled={isLoading}
            aria-label="Refresh predictions"
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border border-border/60 hover:bg-secondary transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <RefreshCw
              className={`size-3 ${isLoading ? 'animate-spin' : ''}`}
              aria-hidden="true"
            />
            {isLoading ? 'Predicting…' : 'Predict Now'}
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md px-3 py-2 mb-4"
        >
          {error}
        </div>
      )}

      {/* Empty state */}
      {predictions.length === 0 && !isLoading && (
        <p className="text-xs text-muted-foreground py-4 text-center">
          No prediction data available yet.
        </p>
      )}

      {/* District cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {predictions.map((p) => {
          const isExtreme = p.is_extreme_event || p.risk === 'severe'
          return (
            <div
              key={`${p.district}-${p.hazard}`}
              className={`rounded-lg border p-4 flex flex-col gap-2 transition-all ${
                isExtreme
                  ? 'border-destructive/60 bg-destructive/10 ring-1 ring-destructive/40 shadow-lg shadow-destructive/10'
                  : 'border-border/50 bg-secondary/20 hover:bg-secondary/40'
              }`}
            >
              {/* District name + risk badge */}
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm truncate max-w-[7rem]">{p.district}</span>
                <RiskBadge risk={p.risk} />
              </div>

              {/* IMD Category badge if present */}
              {p.imd_category && (
                <div className="flex items-center gap-1.5">
                  <span
                    className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                      p.imd_color_code === 'red'
                        ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                        : p.imd_color_code === 'orange'
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        : p.imd_color_code === 'yellow'
                        ? 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                        : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                    }`}
                  >
                    IMD: {p.imd_category.replace(/_/g, ' ')}
                  </span>
                  {p.is_extreme_event && (
                    <span className="text-[10px] font-bold text-destructive animate-pulse">
                      ALERT
                    </span>
                  )}
                </div>
              )}

              {/* Rainfall reading */}
              <div className="flex items-center gap-2 text-muted-foreground">
                <CloudRain className={`size-4 shrink-0 ${iconClass}`} aria-hidden="true" />
                <span className="tabular-nums text-lg font-semibold text-foreground">
                  {p.predicted_rainfall_mm != null ? p.predicted_rainfall_mm.toFixed(2) : '—'}
                </span>
                <span className="text-[11px]">mm/24h</span>
              </div>

              {/* Probability bar */}
              <div className="flex items-center gap-2 mt-1">
                <div
                  className="h-1.5 flex-1 rounded-full bg-secondary overflow-hidden"
                  role="progressbar"
                  aria-valuenow={p.probability}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${p.district} probability ${p.probability}%`}
                >
                  <div
                    className={probabilityBarClass(p.probability)}
                    style={{ width: `${p.probability}%` }}
                  />
                </div>
                <span className="tabular-nums text-xs text-muted-foreground shrink-0">
                  {p.probability}%
                </span>
              </div>

              {/* Action / context footnote */}
              {p.action_recommended && (
                <p className="text-[10px] text-muted-foreground line-clamp-1 mt-0.5" title={p.action_recommended}>
                  {p.action_recommended}
                </p>
              )}

              {/* Confidence */}
              {p.confidence != null && (
                <p className="text-[10px] text-muted-foreground/70">
                  conf. {p.confidence}%
                </p>
              )}
            </div>
          )
        })}
      </div>
    </GlassCard>
  )
}

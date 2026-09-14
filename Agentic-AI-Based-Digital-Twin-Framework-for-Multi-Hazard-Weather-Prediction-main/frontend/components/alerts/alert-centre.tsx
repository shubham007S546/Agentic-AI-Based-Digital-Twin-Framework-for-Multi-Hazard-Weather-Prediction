'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Siren,
  MessageSquare,
  Radio,
  Smartphone,
  CheckCheck,
  RefreshCw,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { ALERTS } from '@/lib/mock/data'
import { getActiveAlerts } from '@/lib/api/alerts'
import type { AlertItem, RiskLevel } from '@/types'
import { cn } from '@/lib/utils'

// ── Constants ────────────────────────────────────────────────────────────────

const SEVERITIES: ('all' | RiskLevel)[] = ['all', 'severe', 'high', 'moderate', 'low']

const CHANNELS = [
  { name: 'SMS (CAP gateway)', icon: Smartphone, reach: '2.4M subscribers', status: 'operational' },
  { name: 'District EOC hotline', icon: Radio, reach: '12 district EOCs', status: 'operational' },
  { name: 'Mobile app push', icon: MessageSquare, reach: '184K devices', status: 'operational' },
  { name: 'Siren network', icon: Siren, reach: '86 villages (Beas basin)', status: 'partial' },
]

const REFRESH_INTERVAL_MS = 60_000   // auto-refresh every 60 seconds
const STALE_THRESHOLD_MS  = 90_000   // data older than 90s is shown as stale

// ── Helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string) {
  const diffMs = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diffMs / 60_000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24)  return `${hrs} h ago`
  return `${Math.round(hrs / 24)} d ago`
}

// ── Sub-components ────────────────────────────────────────────────────────────

interface StatusBarProps {
  lastRefreshed: Date | null
  isLoading: boolean
  isLive: boolean
  isStale: boolean
  onRefresh: () => void
}

function StatusBar({ lastRefreshed, isLoading, isLive, isStale, onRefresh }: StatusBarProps) {
  return (
    <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
      {isLive ? (
        <Wifi className="size-3 text-success shrink-0" aria-hidden="true" />
      ) : (
        <WifiOff className="size-3 text-warning shrink-0" aria-hidden="true" />
      )}
      <span className={cn(isStale && 'text-warning')}>
        {isLive ? 'Live' : 'Offline (mock data)'}
        {lastRefreshed && ` · updated ${timeAgo(lastRefreshed.toISOString())}`}
        {isStale && ' · data may be stale'}
      </span>
      <button
        onClick={onRefresh}
        disabled={isLoading}
        aria-label="Refresh alerts"
        className="ml-auto rounded p-0.5 hover:text-foreground transition-colors disabled:opacity-40"
      >
        <RefreshCw className={cn('size-3', isLoading && 'animate-spin')} aria-hidden="true" />
      </button>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function AlertCentre() {
  const [severity, setSeverity]     = useState<(typeof SEVERITIES)[number]>('all')
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({})

  // Live data state
  const [alerts, setAlerts]         = useState<AlertItem[]>(ALERTS)   // pre-seed with mock
  const [isLoading, setIsLoading]   = useState(false)
  const [isLive, setIsLive]         = useState(false)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Fetch from backend ──────────────────────────────────────────────────
  const fetchAlerts = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true)
    try {
      const data = await getActiveAlerts(50)
      // getActiveAlerts returns the array directly (falls back to mock on error)
      // Detect if we got live data: differs from the static ALERTS length or content
      const isLiveResponse = data !== ALERTS && JSON.stringify(data) !== JSON.stringify(ALERTS)
      setAlerts(data)
      setIsLive(isLiveResponse)
      setLastRefreshed(new Date())
    } catch {
      // Network error — stay on current data, mark as offline
      setIsLive(false)
    } finally {
      if (!silent) setIsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  // Auto-refresh
  useEffect(() => {
    timerRef.current = setInterval(() => fetchAlerts(true), REFRESH_INTERVAL_MS)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [fetchAlerts])

  // Stale check
  const isStale = lastRefreshed
    ? Date.now() - lastRefreshed.getTime() > STALE_THRESHOLD_MS
    : false

  // ── Filtered list ────────────────────────────────────────────────────────
  const filtered = useMemo(
    () => alerts.filter((a) => severity === 'all' || a.severity === severity),
    [alerts, severity],
  )

  // Severity counts (for summary badges)
  const severeCnt  = useMemo(() => alerts.filter((a) => a.severity === 'severe').length, [alerts])
  const highCnt    = useMemo(() => alerts.filter((a) => a.severity === 'high').length, [alerts])

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">

      {/* ── Left: Alert list ─────────────────────────────────────────────── */}
      <div className="xl:col-span-2 flex flex-col gap-4">
        <GlassCard className="p-5">

          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-medium">Active Alerts</h2>
              {severeCnt > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 text-destructive text-[10px] font-semibold px-2 py-0.5 border border-destructive/30">
                  {severeCnt} severe
                </span>
              )}
              {highCnt > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full bg-warning/15 text-warning text-[10px] font-semibold px-2 py-0.5 border border-warning/30">
                  {highCnt} high
                </span>
              )}
            </div>

            {/* Severity filter tabs */}
            <div className="flex items-center gap-1 flex-wrap" role="tablist" aria-label="Filter by severity">
              {SEVERITIES.map((s) => (
                <button
                  key={s}
                  role="tab"
                  aria-selected={severity === s}
                  onClick={() => setSeverity(s)}
                  className={cn(
                    'px-2.5 py-1 rounded-full border text-[11px] font-medium capitalize transition-colors',
                    severity === s
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Status bar */}
          <div className="mb-4">
            <StatusBar
              lastRefreshed={lastRefreshed}
              isLoading={isLoading}
              isLive={isLive}
              isStale={isStale}
              onRefresh={() => fetchAlerts()}
            />
          </div>

          {/* Alert items */}
          <ul className="flex flex-col gap-3" aria-label="Alert list" aria-live="polite" aria-busy={isLoading}>

            {/* Loading skeleton */}
            {isLoading && alerts.length === 0 && (
              Array.from({ length: 3 }).map((_, i) => (
                <li key={i} className="rounded-xl border border-border bg-secondary/30 p-4 animate-pulse">
                  <div className="h-3 w-2/5 bg-secondary rounded mb-2" />
                  <div className="h-2 w-3/5 bg-secondary/60 rounded" />
                </li>
              ))
            )}

            {filtered.map((a) => (
              <li
                key={a.id}
                className={cn(
                  'rounded-xl border p-4 transition-colors',
                  a.severity === 'severe'
                    ? 'border-destructive/40 bg-destructive/5'
                    : a.severity === 'high'
                      ? 'border-warning/40 bg-warning/5'
                      : 'border-border bg-secondary/30',
                )}
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{a.title}</span>
                      <RiskBadge risk={a.severity} />
                    </div>
                    <span className="text-[11px] text-muted-foreground block mt-0.5">
                      {a.district} district · {a.type} · issued {timeAgo(a.issuedAt)}
                    </span>
                  </div>
                  <button
                    onClick={() => setAcknowledged((prev) => ({ ...prev, [a.id]: !prev[a.id] }))}
                    aria-pressed={!!acknowledged[a.id]}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors shrink-0',
                      acknowledged[a.id]
                        ? 'bg-success/15 text-success border-success/30'
                        : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
                    )}
                  >
                    <CheckCheck className="size-3.5" aria-hidden="true" />
                    {acknowledged[a.id] ? 'Acknowledged' : 'Acknowledge'}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-2 text-pretty">{a.message}</p>
              </li>
            ))}

            {!isLoading && filtered.length === 0 && (
              <li className="text-center text-xs text-muted-foreground py-8">
                No alerts at this severity level.
              </li>
            )}
          </ul>
        </GlassCard>
      </div>

      {/* ── Right: Channels + Escalation ────────────────────────────────── */}
      <div className="flex flex-col gap-4">

        {/* Live summary card */}
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Alert Summary</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Total Active', value: alerts.length, accent: '' },
              { label: 'Severe',  value: alerts.filter(a => a.severity === 'severe').length,   accent: 'text-destructive' },
              { label: 'High',    value: alerts.filter(a => a.severity === 'high').length,     accent: 'text-warning' },
              { label: 'Moderate',value: alerts.filter(a => a.severity === 'moderate').length, accent: 'text-yellow-400' },
            ].map(({ label, value, accent }) => (
              <div key={label} className="rounded-lg bg-secondary/50 px-3 py-2 text-center">
                <div className={cn('text-lg font-bold tabular-nums', accent)}>{value}</div>
                <div className="text-[10px] text-muted-foreground">{label}</div>
              </div>
            ))}
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Dispatch Channels</h2>
          <ul className="flex flex-col gap-3">
            {CHANNELS.map((c) => (
              <li key={c.name} className="flex items-center gap-3">
                <div className="size-9 rounded-lg bg-secondary flex items-center justify-center shrink-0">
                  <c.icon className="size-4 text-primary" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="text-xs font-medium block">{c.name}</span>
                  <span className="text-[10px] text-muted-foreground">{c.reach}</span>
                </div>
                <span
                  className={cn(
                    'size-2 rounded-full shrink-0',
                    c.status === 'operational' ? 'bg-success' : 'bg-warning',
                  )}
                  aria-label={c.status}
                />
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Escalation Protocol</h2>
          <ol className="flex flex-col gap-2.5 text-xs text-muted-foreground list-none">
            {[
              'Model probability crosses district threshold',
              'Analyst verifies against radar and gauge data',
              'CAP alert drafted and severity assigned',
              'District EOC and SDMA notified simultaneously',
              'Public channels triggered for severe alerts',
            ].map((step, i) => (
              <li key={step} className="flex gap-2.5">
                <span className="size-5 rounded-full bg-secondary text-foreground flex items-center justify-center text-[10px] font-mono shrink-0">
                  {i + 1}
                </span>
                <span className="text-pretty">{step}</span>
              </li>
            ))}
          </ol>
        </GlassCard>
      </div>
    </div>
  )
}

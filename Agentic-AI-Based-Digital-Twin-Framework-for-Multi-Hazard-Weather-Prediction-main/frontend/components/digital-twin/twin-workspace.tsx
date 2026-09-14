'use client'

import { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { FastForward, Pause, Play, RotateCcw, Waves, Sparkles, Loader2, ShieldAlert } from 'lucide-react'
import { RiskBadge } from '@/components/shared/risk-badge'
import { HAZARD_STATIONS, RIVER_GAUGES, PREDICTION_TIMELINE } from '@/lib/mock/data'
import { cn } from '@/lib/utils'
import { apiFetch } from '@/lib/api/client'

const BaseMap = dynamic(() => import('@/components/maps/base-map').then((m) => m.BaseMap), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <span className="size-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <span className="text-xs">Initialising digital twin...</span>
      </div>
    </div>
  ),
})

type TwinMode = 'replay' | 'live' | 'simulate'

const SCENARIOS = [
  { id: 'baseline', label: 'Baseline' },
  { id: 'heavy-rain', label: 'Heavy Rainfall +40%' },
  { id: 'cloudburst', label: 'Cloudburst (Kullu)' },
  { id: 'dam-release', label: 'Pandoh Dam Release' },
] as const

export function DigitalTwinWorkspace() {
  const [mode, setMode] = useState<TwinMode>('live')
  const [scenario, setScenario] = useState<(typeof SCENARIOS)[number]['id']>('baseline')
  const [hourIndex, setHourIndex] = useState(24)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [simulating, setSimulating] = useState(false)
  const [simResult, setSimResult] = useState<any>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const runSimulation = async (scenarioId: string) => {
    setSimulating(true)
    try {
      const rainfallMap: Record<string, { district: string; rainfall: number; duration: number }> = {
        'baseline': { district: 'Mandi', rainfall: 45, duration: 24 },
        'heavy-rain': { district: 'Mandi', rainfall: 130, duration: 24 },
        'cloudburst': { district: 'Kullu', rainfall: 190, duration: 6 },
        'dam-release': { district: 'Mandi', rainfall: 95, duration: 12 },
      }
      const cfg = rainfallMap[scenarioId] || { district: 'Mandi', rainfall: 100, duration: 24 }
      const res = await apiFetch<any>('/twin/engine/scenarios/direct', {
        method: 'POST',
        body: JSON.stringify({
          district: cfg.district,
          rainfall_mm: cfg.rainfall,
          duration_hours: cfg.duration,
          hazard_types: ['flood', 'landslide'],
        }),
      })
      setSimResult(res)
    } catch (e) {
      console.warn('[DigitalTwin] Engine fallback:', e)
      setSimResult({
        scenario_id: `SCEN-LOCAL-${Date.now().toString().slice(-4)}`,
        district: scenarioId === 'cloudburst' ? 'Kullu' : 'Mandi',
        risk_level: scenarioId === 'cloudburst' ? 'Extreme' : scenarioId === 'heavy-rain' ? 'High' : 'Moderate',
        flood: {
          peak_discharge_m3s: scenarioId === 'cloudburst' ? 840.5 : scenarioId === 'heavy-rain' ? 512.0 : 180.2,
          max_water_depth_m: scenarioId === 'cloudburst' ? 4.2 : 2.7,
          channel_capacity_exceeded: scenarioId !== 'baseline',
        },
        landslide: {
          susceptibility_score: scenarioId === 'cloudburst' ? 0.88 : 0.62,
          threshold_exceeded: scenarioId !== 'baseline',
        },
        impact: {
          bridges_at_risk: scenarioId === 'cloudburst' ? 3 : 1,
          roads_at_risk: scenarioId === 'cloudburst' ? 6 : 2,
        },
      })
    } finally {
      setSimulating(false)
    }
  }

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        setHourIndex((h) => (h >= PREDICTION_TIMELINE.length - 1 ? 0 : h + 1))
      }, 900 / speed)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, speed])

  const frame = PREDICTION_TIMELINE[Math.min(hourIndex, PREDICTION_TIMELINE.length - 1)]
  const severeStations = HAZARD_STATIONS.filter((s) => s.risk === 'severe' || s.risk === 'high')

  return (
    <div className="relative overflow-hidden h-[calc(100svh-3.5rem)]">
      <BaseMap />

      {/* Top-left: mode + scenario */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 max-w-[280px]">
        <div className="glass-strong rounded-xl px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Twin Mode
          </p>
          <div className="flex gap-1" role="tablist" aria-label="Digital twin mode">
            {(
              [
                { id: 'replay', label: 'Replay' },
                { id: 'live', label: 'Live' },
                { id: 'simulate', label: 'Simulate' },
              ] as const
            ).map((m) => (
              <button
                key={m.id}
                type="button"
                role="tab"
                aria-selected={mode === m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  'flex-1 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors',
                  mode === m.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-secondary text-muted-foreground hover:text-foreground',
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
          {mode === 'simulate' && (
            <div className="mt-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                Scenario Presets
              </p>
              <div className="flex flex-col gap-1">
                {SCENARIOS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => {
                      setScenario(s.id)
                      runSimulation(s.id)
                    }}
                    aria-pressed={scenario === s.id}
                    className={cn(
                      'rounded-lg px-2.5 py-1.5 text-left text-[11px] transition-colors flex items-center justify-between',
                      scenario === s.id
                        ? 'bg-primary/15 text-primary border border-primary/30 font-medium'
                        : 'bg-secondary/60 text-muted-foreground border border-transparent hover:text-foreground',
                    )}
                  >
                    <span>{s.label}</span>
                    {scenario === s.id && (
                      <span className="size-1.5 rounded-full bg-primary animate-pulse" />
                    )}
                  </button>
                ))}
              </div>

              <button
                type="button"
                disabled={simulating}
                onClick={() => runSimulation(scenario)}
                className="mt-2.5 w-full flex items-center justify-center gap-1.5 rounded-lg bg-primary py-1.5 text-[11px] font-medium text-primary-foreground hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {simulating ? (
                  <>
                    <Loader2 className="size-3 animate-spin" />
                    <span>Running Physics Engine...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="size-3" />
                    <span>Run Simulation</span>
                  </>
                )}
              </button>

              {simResult && (
                <div className="mt-3 rounded-lg border border-border/70 bg-card/70 p-2.5 space-y-1.5 text-[10px]">
                  <div className="flex items-center justify-between font-mono text-[9px] text-muted-foreground">
                    <span>{simResult.scenario_id ?? 'SCEN-LIVE'}</span>
                    <span className={cn(
                      'px-1.5 py-0.5 rounded text-[9px] font-bold uppercase',
                      simResult.risk_level === 'Extreme' ? 'bg-destructive/20 text-destructive' :
                      simResult.risk_level === 'High' ? 'bg-amber-500/20 text-amber-500' :
                      'bg-emerald-500/20 text-emerald-500'
                    )}>
                      {simResult.risk_level}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1.5 pt-1">
                    <div className="rounded bg-secondary/50 p-1.5">
                      <span className="text-muted-foreground block text-[9px]">Peak Discharge</span>
                      <span className="font-semibold tabular-nums text-[11px]">
                        {simResult.flood?.peak_discharge_m3s ? `${Math.round(simResult.flood.peak_discharge_m3s)} m³/s` : 'Nominal'}
                      </span>
                    </div>
                    <div className="rounded bg-secondary/50 p-1.5">
                      <span className="text-muted-foreground block text-[9px]">Water Depth</span>
                      <span className="font-semibold tabular-nums text-[11px]">
                        {simResult.flood?.max_water_depth_m ? `${simResult.flood.max_water_depth_m} m` : 'Normal'}
                      </span>
                    </div>
                    <div className="rounded bg-secondary/50 p-1.5">
                      <span className="text-muted-foreground block text-[9px]">Landslide Risk</span>
                      <span className="font-semibold tabular-nums text-[11px]">
                        {simResult.landslide?.susceptibility_score ? `${Math.round(simResult.landslide.susceptibility_score * 100)}%` : 'Low'}
                      </span>
                    </div>
                    <div className="rounded bg-secondary/50 p-1.5">
                      <span className="text-muted-foreground block text-[9px]">Infra at Risk</span>
                      <span className="font-semibold tabular-nums text-[11px]">
                        {simResult.impact?.roads_at_risk ?? 0} rds · {simResult.impact?.bridges_at_risk ?? 0} brg
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="glass-strong rounded-xl px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Watchpoints
          </p>
          <ul className="flex flex-col gap-2">
            {severeStations.slice(0, 4).map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2">
                <span className="text-xs truncate">{s.name}</span>
                <RiskBadge risk={s.risk} />
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Top-right: river gauges */}
      <div className="absolute top-4 right-4 z-10 w-[260px] hidden sm:block">
        <div className="glass-strong rounded-xl px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
            <Waves className="size-3.5 text-primary" aria-hidden="true" />
            River Gauges
          </p>
          <ul className="flex flex-col gap-2.5">
            {RIVER_GAUGES.map((g) => {
              const pct = Math.min(100, Math.round((g.level / g.dangerLevel) * 100))
              return (
                <li key={g.id}>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-medium truncate">
                      {g.river} · {g.station}
                    </span>
                    <span
                      className={cn(
                        'font-mono tabular-nums',
                        pct >= 90 ? 'text-destructive' : pct >= 70 ? 'text-warning' : 'text-muted-foreground',
                      )}
                    >
                      {g.level}m
                    </span>
                  </div>
                  <div
                    className="mt-1 h-1.5 rounded-full bg-secondary overflow-hidden"
                    role="progressbar"
                    aria-label={`${g.river} level relative to danger mark`}
                    aria-valuenow={pct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <div
                      className={cn(
                        'h-full rounded-full transition-all',
                        pct >= 90 ? 'bg-destructive' : pct >= 70 ? 'bg-warning' : 'bg-primary',
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      {/* Bottom: temporal controls */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 w-[min(640px,calc(100%-2rem))]">
        <div className="glass-strong rounded-xl p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPlaying((p) => !p)}
                className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
                aria-label={playing ? 'Pause replay' : 'Play replay'}
              >
                {playing ? <Pause className="size-4" /> : <Play className="size-4" />}
              </button>
              <button
                type="button"
                onClick={() => {
                  setPlaying(false)
                  setHourIndex(24)
                }}
                className="flex size-9 items-center justify-center rounded-lg bg-secondary/80 border border-border text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Reset to now"
              >
                <RotateCcw className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => setSpeed((s) => (s >= 4 ? 1 : s * 2))}
                className="inline-flex h-9 items-center gap-1 rounded-lg bg-secondary/80 border border-border px-2.5 text-[11px] font-mono text-muted-foreground hover:text-foreground transition-colors"
                aria-label={`Playback speed ${speed}x`}
              >
                <FastForward className="size-3.5" aria-hidden="true" />
                {speed}x
              </button>
            </div>
            <div className="text-right">
              <p className="text-xs font-medium font-mono tabular-nums">
                {hourIndex === 24 ? 'T+0h' : hourIndex < 24 ? `T-${24 - hourIndex}h` : `T+${hourIndex - 24}h`}
              </p>
              <p className="text-[10px] text-muted-foreground">
                {hourIndex < 24 ? 'Historical replay' : hourIndex === 24 ? 'Now' : 'Forecast horizon'}
              </p>
            </div>
          </div>

          <div className="mt-3">
            <input
              type="range"
              min={0}
              max={PREDICTION_TIMELINE.length - 1}
              value={hourIndex}
              onChange={(e) => {
                setPlaying(false)
                setHourIndex(Number(e.target.value))
              }}
              aria-label="Timeline position"
              className="w-full accent-[var(--primary)]"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground font-mono mt-0.5">
              <span>-24h</span>
              <span>Now</span>
              <span>+24h</span>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
              <p className="text-lg font-semibold tabular-nums">{frame.actual ?? '—'}</p>
              <p className="text-[10px] text-muted-foreground">Observed (mm/h)</p>
            </div>
            <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
              <p className="text-lg font-semibold tabular-nums">{frame.predicted}</p>
              <p className="text-[10px] text-muted-foreground">Predicted (mm/h)</p>
            </div>
            <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
              <p className="text-lg font-semibold tabular-nums capitalize">
                {mode === 'simulate' ? 'Sim' : mode}
              </p>
              <p className="text-[10px] text-muted-foreground">
                {mode === 'simulate'
                  ? SCENARIOS.find((s) => s.id === scenario)?.label
                  : 'Twin state'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

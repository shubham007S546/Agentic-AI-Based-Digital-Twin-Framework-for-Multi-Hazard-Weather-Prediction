'use client'

import { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { FastForward, Pause, Play, RotateCcw, Waves } from 'lucide-react'
import { RiskBadge } from '@/components/shared/risk-badge'
import { PREDICTION_TIMELINE } from '@/lib/mock/data'
import { cn } from '@/lib/utils'
import type { HazardStation, RiverGauge } from '@/types'

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

interface DigitalTwinWorkspaceProps {
  initialStations: HazardStation[]
  initialGauges: RiverGauge[]
}

export function DigitalTwinWorkspace({ initialStations, initialGauges }: DigitalTwinWorkspaceProps) {
  const [mode, setMode] = useState<TwinMode>('live')
  const [scenario, setScenario] = useState<(typeof SCENARIOS)[number]['id']>('baseline')
  const [hourIndex, setHourIndex] = useState(24)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
  const severeStations = initialStations.filter((s) => s.risk === 'severe' || s.risk === 'high')

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
                Scenario
              </p>
              <div className="flex flex-col gap-1">
                {SCENARIOS.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setScenario(s.id)}
                    aria-pressed={scenario === s.id}
                    className={cn(
                      'rounded-lg px-2.5 py-1.5 text-left text-[11px] transition-colors',
                      scenario === s.id
                        ? 'bg-primary/15 text-primary border border-primary/30'
                        : 'bg-secondary/60 text-muted-foreground border border-transparent hover:text-foreground',
                    )}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
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
            {initialGauges.map((g) => {
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

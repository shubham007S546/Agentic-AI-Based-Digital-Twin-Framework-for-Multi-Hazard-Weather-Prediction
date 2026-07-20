'use client'

import { useState } from 'react'
import dynamic from 'next/dynamic'
import { Maximize2, Minimize2, PanelRightOpen, X } from 'lucide-react'
import { LayersPanel } from './layers-panel'
import { RiskBadge } from '@/components/shared/risk-badge'
import { useAppStore } from '@/store/use-app-store'
import { cn } from '@/lib/utils'
import type { WeatherSnapshot, HazardStation, AlertItem } from '@/types'

const BaseMap = dynamic(() => import('./base-map').then((m) => m.BaseMap), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <span className="size-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <span className="text-xs">Loading geospatial engine...</span>
      </div>
    </div>
  ),
})

interface MapWorkspaceProps {
  initialWeather: WeatherSnapshot
  initialStations: HazardStation[]
  initialAlerts: AlertItem[]
}

export function MapWorkspace({
  initialWeather,
  initialStations,
  initialAlerts,
}: MapWorkspaceProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [layersOpen, setLayersOpen] = useState(true)
  const fullscreen = useAppStore((s) => s.mapFullscreen)
  const setFullscreen = useAppStore((s) => s.setMapFullscreen)

  const selected = initialStations.find((s) => s.id === selectedId)

  return (
    <div
      className={cn(
        'relative overflow-hidden',
        fullscreen ? 'fixed inset-0 z-50 bg-background' : 'h-[calc(100svh-3.5rem)]',
      )}
    >
      <BaseMap onStationClick={setSelectedId} stations={initialStations} />

      {/* Top-left: legend / status */}
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 max-w-[260px]">
        <div className="glass-strong rounded-xl px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Region Status
          </p>
          <p className="text-sm mt-1">
            {initialWeather.condition} · {initialWeather.temperature}°C
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            {(['low', 'moderate', 'high', 'severe'] as const).map((r) => (
              <span key={r} className="inline-flex items-center gap-1.5 capitalize text-muted-foreground">
                <span
                  className={cn(
                    'size-2 rounded-full',
                    r === 'low' && 'bg-success',
                    r === 'moderate' && 'bg-warning',
                    r === 'high' && 'bg-warning brightness-90',
                    r === 'severe' && 'bg-destructive',
                  )}
                />
                {r}
              </span>
            ))}
          </div>
        </div>

        <div className="glass-strong rounded-xl px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Active Alerts
          </p>
          <ul className="flex flex-col gap-2">
            {initialAlerts.slice(0, 3).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <span className="text-xs truncate">{a.title}</span>
                <RiskBadge risk={a.severity} />
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Top-right: controls */}
      <div className="absolute top-4 right-4 z-10 flex flex-col items-end gap-2">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setLayersOpen((v) => !v)}
            className="glass-strong flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Toggle layers panel"
          >
            <PanelRightOpen className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => setFullscreen(!fullscreen)}
            className="glass-strong flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground transition-colors"
            aria-label={fullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </button>
        </div>
        {layersOpen && <LayersPanel />}
      </div>

      {/* Bottom: station detail */}
      {selected && (
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 w-[min(480px,calc(100%-2rem))]">
          <div className="glass-strong rounded-xl p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{selected.name}</h3>
                  <RiskBadge risk={selected.risk} />
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {selected.district} district · {selected.lat.toFixed(3)}, {selected.lng.toFixed(3)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                aria-label="Close station detail"
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
                <p className="text-lg font-semibold tabular-nums">{selected.probability}%</p>
                <p className="text-[10px] text-muted-foreground">Hazard probability</p>
              </div>
              <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
                <p className="text-lg font-semibold tabular-nums">{selected.metric}</p>
                <p className="text-[10px] text-muted-foreground">24h rainfall (mm)</p>
              </div>
              <div className="rounded-lg bg-secondary/60 p-2.5 text-center">
                <p className="text-lg font-semibold tabular-nums">TFT</p>
                <p className="text-[10px] text-muted-foreground">Prediction model</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

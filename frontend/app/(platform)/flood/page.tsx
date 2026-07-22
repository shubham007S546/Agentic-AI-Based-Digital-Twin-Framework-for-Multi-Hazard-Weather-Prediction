import type { Metadata } from 'next'
import { Waves, TrendingUp, Timer, Droplets, ArrowUp, ArrowDown, Minus, CloudRain } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { GenericAreaChart } from '@/components/charts/extra-charts'
import { RIVER_GAUGES } from '@/lib/mock/data'
import { getFloodPredictions } from '@/lib/api/predictions'

export const metadata: Metadata = {
  title: 'Flood Prediction | VARUNA',
  description: 'River-level forecasting and flood inundation risk for major basins.',
}

// NOTE: river-stage forecast below is illustrative (mock) -- the backend
// does not yet expose per-gauge river-level/discharge data, only
// district-level rainfall predictions (see LIVE section above the fold).
const LEVEL_FORECAST = Array.from({ length: 36 }, (_, i) => ({
  hour: `+${i}h`,
  level: Number((8.4 + Math.min(2.4, i * 0.09) - (i > 22 ? (i - 22) * 0.06 : 0)).toFixed(2)),
  danger: 10.2,
}))

const TREND_ICON = { rising: ArrowUp, falling: ArrowDown, steady: Minus }
const TREND_CLASS = { rising: 'text-destructive', falling: 'text-success', steady: 'text-muted-foreground' }

export default async function FloodPage() {
  // Real, live prediction from the trained LSTM model (falls back to mock
  // automatically if the backend is unreachable -- see fetchWithFallback).
  const predictions = await getFloodPredictions()

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Flood Prediction"
        description="Hydrological routing and AI river-stage forecasting for Beas, Sutlej, Ravi and Parvati basins with dam-inflow awareness."
      />

      <section aria-label="Flood indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Basins on Watch" value="2" icon={Waves} sub="Beas · Parvati" tone="warning" />
        <StatCard label="Pandoh Inflow" value="1240" unit="m³/s" icon={TrendingUp} sub="+18% in 6h" tone="danger" />
        <StatCard label="Time to Danger" value="~14" unit="h" icon={Timer} sub="Beas at Pandoh (projected)" tone="warning" />
        <StatCard label="Soil Saturation" value="86" unit="%" icon={Droplets} sub="Top 1m layer, basin mean" tone="warning" />
      </section>

      {/* ── LIVE: real LSTM model predictions per district ───────────── */}
      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">District Rainfall Risk — Live</h2>
          <span className="text-[10px] font-mono text-muted-foreground">
            {predictions[0]?.confidence ? `model: lstm_v1 · ${predictions.length} districts` : 'live'}
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {predictions.map((p) => (
            <div key={p.district} className="rounded-lg border border-border/50 p-4 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">{p.district}</span>
                <RiskBadge risk={p.risk} />
              </div>
              <div className="flex items-center gap-2 text-muted-foreground">
                <CloudRain className="size-4" aria-hidden="true" />
                <span className="tabular-nums text-lg font-semibold text-foreground">
                  {p.predicted_rainfall_mm?.toFixed(2) ?? '—'}
                </span>
                <span className="text-xs">mm predicted (next hr)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="h-1.5 flex-1 rounded-full bg-secondary overflow-hidden">
                  <div
                    className={p.probability > 60 ? 'h-full bg-destructive' : p.probability > 30 ? 'h-full bg-warning' : 'h-full bg-primary'}
                    style={{ width: `${p.probability}%` }}
                  />
                </div>
                <span className="tabular-nums text-xs text-muted-foreground">{p.probability}%</span>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Beas at Pandoh — 36h Stage Forecast</h2>
          <span className="text-[10px] font-mono text-muted-foreground">illustrative · danger 10.2m</span>
        </div>
        <GenericAreaChart
          data={LEVEL_FORECAST}
          xKey="hour"
          unit="m"
          interval={5}
          series={[
            { key: 'level', name: 'Forecast level' },
            { key: 'danger', name: 'Danger mark', color: 'oklch(0.64 0.2 25)', dashed: true },
          ]}
        />
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">River Gauge Network</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">River</th>
                <th className="pb-2 pr-4 font-medium">Station</th>
                <th className="pb-2 pr-4 font-medium">Level</th>
                <th className="pb-2 pr-4 font-medium">Danger</th>
                <th className="pb-2 pr-4 font-medium">Discharge</th>
                <th className="pb-2 pr-4 font-medium">Capacity</th>
                <th className="pb-2 font-medium">Trend</th>
              </tr>
            </thead>
            <tbody>
              {RIVER_GAUGES.map((g) => {
                const pct = Math.min(100, Math.round((g.level / g.dangerLevel) * 100))
                const TrendIcon = TREND_ICON[g.trend]
                return (
                  <tr key={g.id} className="border-b border-border/50 last:border-0">
                    <td className="py-2.5 pr-4 font-medium">{g.river}</td>
                    <td className="py-2.5 pr-4 text-muted-foreground">{g.station}</td>
                    <td className="py-2.5 pr-4 tabular-nums">{g.level} m</td>
                    <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">{g.dangerLevel} m</td>
                    <td className="py-2.5 pr-4 tabular-nums">{g.discharge} m³/s</td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 rounded-full bg-secondary overflow-hidden">
                          <div
                            className={pct > 80 ? 'h-full bg-destructive' : pct > 60 ? 'h-full bg-warning' : 'h-full bg-primary'}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                        <span className="tabular-nums text-xs">{pct}%</span>
                      </div>
                    </td>
                    <td className="py-2.5">
                      <span className={`flex items-center gap-1 text-xs capitalize ${TREND_CLASS[g.trend]}`}>
                        <TrendIcon className="size-3.5" aria-hidden="true" />
                        {g.trend}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

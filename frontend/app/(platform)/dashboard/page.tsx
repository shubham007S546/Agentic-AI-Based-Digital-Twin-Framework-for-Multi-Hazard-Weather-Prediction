import type { Metadata } from 'next'
import {
  CloudRain,
  Droplets,
  Thermometer,
  Gauge,
  Wind,
  CloudLightning,
  Waves,
  Leaf,
  Bot,
  Database,
  Building2,
  Target,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { HourlyRainfallChart, MonthlyRainfallChart } from '@/components/charts/charts'
import { CURRENT_WEATHER, RIVER_GAUGES, ALERTS, DATASETS, HAZARD_STATIONS } from '@/lib/mock/data'
import { MiniMapCard } from '@/components/maps/mini-map-card'

export const metadata: Metadata = {
  title: 'Dashboard | Digital Twin',
  description: 'Live situational overview: weather, hazards, hydrology and AI status.',
}

export default function DashboardPage() {
  const severeCount = HAZARD_STATIONS.filter((s) => s.risk === 'severe' || s.risk === 'high').length

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Situational Dashboard"
        description="Live overview of weather, hazard risk, hydrology and platform intelligence for Himachal Pradesh."
      />

      <section
        aria-label="Key metrics"
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3"
      >
        <StatCard label="Rainfall (1h)" value={CURRENT_WEATHER.rainfall} unit="mm" icon={CloudRain} sub="GPM + station fused" />
        <StatCard label="Temperature" value={CURRENT_WEATHER.temperature} unit="°C" icon={Thermometer} sub={CURRENT_WEATHER.condition} />
        <StatCard label="Humidity" value={CURRENT_WEATHER.humidity} unit="%" icon={Droplets} sub={`Dew point ${CURRENT_WEATHER.dewPoint}°C`} />
        <StatCard label="Pressure" value={CURRENT_WEATHER.pressure} unit="hPa" icon={Gauge} sub="Falling 2.1 hPa / 3h" tone="warning" />
        <StatCard label="Wind" value={CURRENT_WEATHER.windSpeed} unit="km/h" icon={Wind} sub={`Direction ${CURRENT_WEATHER.windDirection}`} />
        <StatCard label="Cloudburst Risk" value="91" unit="%" icon={CloudLightning} sub="Upper Beas basin" tone="danger" />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <GlassCard className="p-5 xl:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Rainfall — Observed vs Predicted (24h)</h2>
            <span className="text-[10px] font-mono text-muted-foreground">GPM · ERA5 · XGBoost</span>
          </div>
          <HourlyRainfallChart />
        </GlassCard>

        <MiniMapCard />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">River Levels</h2>
          <ul className="flex flex-col gap-3">
            {RIVER_GAUGES.map((g) => {
              const pct = Math.min(100, Math.round((g.level / g.dangerLevel) * 100))
              return (
                <li key={g.id}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-medium">
                      {g.river} <span className="text-muted-foreground">· {g.station}</span>
                    </span>
                    <span className="tabular-nums text-muted-foreground">
                      {g.level}m / {g.dangerLevel}m
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
                    <div
                      className={pct > 80 ? 'h-full bg-destructive' : pct > 60 ? 'h-full bg-warning' : 'h-full bg-primary'}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              )
            })}
          </ul>
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Active Alerts</h2>
          <ul className="flex flex-col gap-3">
            {ALERTS.map((a) => (
              <li key={a.id} className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm truncate">{a.title}</p>
                  <p className="text-xs text-muted-foreground">{a.district} · {a.type}</p>
                </div>
                <RiskBadge risk={a.severity} />
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard className="p-5 flex flex-col gap-4">
          <h2 className="text-sm font-medium">Platform Intelligence</h2>
          <ul className="flex flex-col gap-3 text-sm">
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Bot className="size-4 text-primary" aria-hidden="true" />AI Agent status</span>
              <span className="text-success text-xs font-medium">Monitoring</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Target className="size-4 text-primary" aria-hidden="true" />Prediction confidence</span>
              <span className="tabular-nums text-xs font-medium">87.4%</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Database className="size-4 text-primary" aria-hidden="true" />Data sources online</span>
              <span className="tabular-nums text-xs font-medium">{DATASETS.length} / {DATASETS.length}</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Leaf className="size-4 text-primary" aria-hidden="true" />Regional NDVI</span>
              <span className="tabular-nums text-xs font-medium">0.64</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Building2 className="size-4 text-primary" aria-hidden="true" />Infrastructure at risk</span>
              <span className="tabular-nums text-xs font-medium text-warning">{severeCount} zones</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-muted-foreground"><Waves className="size-4 text-primary" aria-hidden="true" />Flood watch basins</span>
              <span className="tabular-nums text-xs font-medium text-warning">2</span>
            </li>
          </ul>
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Monthly Rainfall vs Climatological Normal</h2>
          <span className="text-[10px] font-mono text-muted-foreground">IMD · ERA5-Land</span>
        </div>
        <MonthlyRainfallChart />
      </GlassCard>
    </div>
  )
}

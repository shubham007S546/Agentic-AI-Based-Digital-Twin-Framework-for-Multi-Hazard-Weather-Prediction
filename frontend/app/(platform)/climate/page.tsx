import type { Metadata } from 'next'
import { Thermometer, CloudRain, Flame, Globe2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericAreaChart, GenericBarChart } from '@/components/charts/extra-charts'
import {
  TEMP_ANOMALY,
  PRECIP_ANOMALY,
  EXTREME_EVENT_TREND,
  CLIMATE_INDICES,
} from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Climate | VARUNA',
  description: 'Long-term climate trends, teleconnection indices and extreme-event frequency.',
}

export default function ClimatePage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Climate Dashboard"
        description="34-year climate baselines, teleconnection indices and the accelerating trend in extreme-event frequency across the western Himalaya."
      />

      <section aria-label="Climate indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Warming Trend" value="+0.045" unit="°C/yr" icon={Thermometer} sub="1992–2026 linear fit" tone="warning" />
        <StatCard label="Monsoon LPA" value="112" unit="%" icon={CloudRain} sub="Season-to-date exceedance" />
        <StatCard label="Extreme Events" value="+375" unit="%" icon={Flame} sub="Cloudbursts, 1990s vs 2020s" tone="danger" />
        <StatCard label="ENSO State" value="+0.8" icon={Globe2} sub="Weak El Niño (ONI)" />
      </section>

      <div className="grid lg:grid-cols-2 gap-6">
        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Temperature Anomaly</h2>
            <span className="text-[10px] font-mono text-muted-foreground">vs 1981–2010 baseline</span>
          </div>
          <GenericAreaChart
            data={TEMP_ANOMALY}
            xKey="year"
            unit="°"
            interval={5}
            series={[{ key: 'anomaly', name: 'Anomaly', color: 'oklch(0.8 0.15 80)' }]}
          />
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Precipitation Anomaly</h2>
            <span className="text-[10px] font-mono text-muted-foreground">% departure from normal</span>
          </div>
          <GenericAreaChart
            data={PRECIP_ANOMALY}
            xKey="year"
            unit="%"
            interval={5}
            series={[{ key: 'anomaly', name: 'Anomaly' }]}
          />
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Extreme-Event Frequency by Decade</h2>
          <span className="text-[10px] font-mono text-muted-foreground">HPSDMA event catalogue</span>
        </div>
        <GenericBarChart
          data={EXTREME_EVENT_TREND}
          xKey="decade"
          series={[
            { key: 'cloudbursts', name: 'Cloudbursts' },
            { key: 'floods', name: 'Floods' },
            { key: 'landslides', name: 'Landslides' },
          ]}
        />
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Teleconnection Indices — Current State</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {CLIMATE_INDICES.map((ci) => (
            <div key={ci.index} className="rounded-lg border border-border bg-secondary/40 p-4 flex flex-col gap-1.5">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{ci.index}</span>
              <span className="text-2xl font-semibold tabular-nums">{ci.value}</span>
              <span className="text-xs text-primary">{ci.phase}</span>
              <span className="text-xs text-muted-foreground text-pretty">{ci.influence}</span>
            </div>
          ))}
        </div>
      </GlassCard>
    </div>
  )
}

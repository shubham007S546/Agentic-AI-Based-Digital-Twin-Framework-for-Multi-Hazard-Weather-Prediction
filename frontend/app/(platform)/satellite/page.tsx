import type { Metadata } from 'next'
import { Satellite, Radar, CloudDownload, SignalHigh } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericAreaChart } from '@/components/charts/extra-charts'
import { SATELLITE_PASSES, CLOUD_TOP_TEMP } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Satellite Monitoring | VARUNA',
  description: 'Multi-mission satellite pass schedule, ingestion status and convective monitoring.',
}

export default function SatellitePage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Satellite Monitoring"
        description="Multi-mission constellation feeding the platform: precipitation radar, optical imagers and SAR — with live pass schedule and ingestion health."
      />

      <section aria-label="Satellite indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active Missions" value={SATELLITE_PASSES.length} icon={Satellite} sub="6 nominal · 1 degraded" />
        <StatCard label="IMERG Latency" value="3.7" unit="h" icon={CloudDownload} sub="Observation to ingestion" tone="success" />
        <StatCard label="Granules Today" value="184" icon={SignalHigh} sub="0 gaps detected" tone="success" />
        <StatCard label="Min Cloud-Top Temp" value="-68" unit="°C" icon={Radar} sub="Upper Beas cell, INSAT-3DR" tone="danger" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Cloud-Top Temperature — Convective Cell Tracking</h2>
          <span className="text-[10px] font-mono text-muted-foreground">INSAT-3DR IR · cloudburst threshold −65°C</span>
        </div>
        <GenericAreaChart
          data={CLOUD_TOP_TEMP}
          xKey="hour"
          unit="°"
          interval={3}
          height={280}
          series={[
            { key: 'ctt', name: 'Cloud-top temp' },
            { key: 'threshold', name: 'Deep convection threshold', color: 'oklch(0.64 0.2 25)', dashed: true },
          ]}
        />
        <p className="text-xs text-muted-foreground mt-3 text-pretty">
          Sustained cloud-top temperatures below −65°C indicate overshooting convective tops —
          the strongest satellite precursor of cloudburst-scale rainfall rates over complex terrain.
        </p>
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Constellation Pass Schedule</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">Satellite</th>
                <th className="pb-2 pr-4 font-medium">Sensor</th>
                <th className="pb-2 pr-4 font-medium">Next Pass</th>
                <th className="pb-2 pr-4 font-medium">Revisit</th>
                <th className="pb-2 pr-4 font-medium">Product</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {SATELLITE_PASSES.map((s) => (
                <tr key={s.satellite} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{s.satellite}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{s.sensor}</td>
                  <td className="py-2.5 pr-4 font-mono text-xs">{s.nextPass}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{s.revisit}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{s.product}</td>
                  <td className="py-2.5">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs capitalize',
                        s.status === 'nominal'
                          ? 'bg-success/15 text-success border-success/30'
                          : 'bg-warning/15 text-warning border-warning/30',
                      )}
                    >
                      <span className="size-1.5 rounded-full bg-current" />
                      {s.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

import type { Metadata } from 'next'
import { CloudLightning, Zap, Timer, MapPin } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { ProbabilityGauge, GenericAreaChart } from '@/components/charts/extra-charts'
import { HAZARD_STATIONS, ALERTS } from '@/lib/mock/data'
import { getCloudburstPredictions } from '@/lib/api/predictions'
import { LiveDistrictRisk } from '@/components/predictions/live-district-risk'

export const metadata: Metadata = {
  title: 'Cloudburst Prediction | VARUNA',
  description: 'Convective cell tracking and cloudburst probability across high-risk basins.',
}

// NOTE: CAPE time series below is illustrative (mock) -- the backend does
// not yet expose an hourly CAPE series endpoint, only district-level
// rainfall predictions (see LIVE section above the fold).
const CAPE_SERIES = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  cape: Math.round(Math.max(200, 900 + Math.sin(i / 3.1) * 700 + i * 42)),
  shear: Number((8 + Math.sin(i / 4) * 4 + i * 0.18).toFixed(1)),
}))

const BASINS = [
  { name: 'Upper Beas (Manali)', probability: 91, risk: 'severe' as const, window: '0–6h' },
  { name: 'Parvati Valley', probability: 84, risk: 'severe' as const, window: '2–8h' },
  { name: 'Tirthan Valley', probability: 68, risk: 'high' as const, window: '6–12h' },
  { name: 'Upper Sutlej (Rampur)', probability: 54, risk: 'moderate' as const, window: '12–24h' },
  { name: 'Pabbar Basin', probability: 38, risk: 'moderate' as const, window: '24–48h' },
  { name: 'Ravi Headwaters', probability: 22, risk: 'low' as const, window: '—' },
]

export default async function CloudburstPage() {
  const predictions = await getCloudburstPredictions()
  const cloudburstAlert = ALERTS.find((a) => a.type === 'Cloudburst')
  const topDistrict = [...predictions].sort((a, b) => b.probability - a.probability)[0]

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Cloudburst Prediction"
        description="Convective initiation tracking using CAPE, wind shear, cloud-top cooling and terrain forcing signals across Himalayan basins."
      />

      {cloudburstAlert && (
        <GlassCard className="p-4 border-destructive/40 flex items-start gap-3">
          <CloudLightning className="size-5 text-destructive mt-0.5 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-sm font-semibold">{cloudburstAlert.title}</h2>
              <RiskBadge risk={cloudburstAlert.severity} />
            </div>
            <p className="text-xs text-muted-foreground mt-1 text-pretty">{cloudburstAlert.message}</p>
          </div>
        </GlassCard>
      )}

      <section aria-label="Convective indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="CAPE" value="2140" unit="J/kg" icon={Zap} sub="Strongly unstable" tone="danger" />
        <StatCard label="Cloud-top Cooling" value="-9.4" unit="K/15min" icon={CloudLightning} sub="Rapid glaciation" tone="danger" />
        <StatCard label="Lead Time" value="4.2" unit="h" icon={Timer} sub="Estimated onset window" tone="warning" />
        <StatCard label="Cells Tracked" value="7" icon={MapPin} sub="3 intensifying" tone="warning" />
      </section>

      <LiveDistrictRisk hazard="cloudburst" initialData={predictions} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <GlassCard className="p-5 flex flex-col">
          <h2 className="text-sm font-medium mb-2">Event Probability (6h)</h2>
          <ProbabilityGauge value={topDistrict?.probability ?? 0} label={topDistrict?.district ?? '—'} />
          <p className="text-xs text-muted-foreground text-pretty mt-2">
            Live LSTM rainfall model, highest-risk district shown. Threshold for severe watch: 75%.
          </p>
        </GlassCard>

        <GlassCard className="p-5 xl:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">CAPE Evolution (24h)</h2>
            <span className="text-[10px] font-mono text-muted-foreground">illustrative</span>
          </div>
          <GenericAreaChart
            data={CAPE_SERIES}
            xKey="hour"
            unit=" J/kg"
            interval={3}
            series={[{ key: 'cape', name: 'CAPE' }]}
          />
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Basin Watchlist</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">Basin</th>
                <th className="pb-2 pr-4 font-medium">Probability</th>
                <th className="pb-2 pr-4 font-medium">Onset Window</th>
                <th className="pb-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {BASINS.map((b) => (
                <tr key={b.name} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{b.name}</td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 rounded-full bg-secondary overflow-hidden">
                        <div
                          className={
                            b.probability > 75
                              ? 'h-full bg-destructive'
                              : b.probability > 50
                                ? 'h-full bg-warning'
                                : 'h-full bg-primary'
                          }
                          style={{ width: `${b.probability}%` }}
                        />
                      </div>
                      <span className="tabular-nums text-xs">{b.probability}%</span>
                    </div>
                  </td>
                  <td className="py-2.5 pr-4 text-muted-foreground tabular-nums">{b.window}</td>
                  <td className="py-2.5"><RiskBadge risk={b.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

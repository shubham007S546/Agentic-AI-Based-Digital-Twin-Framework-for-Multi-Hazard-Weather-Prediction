import type { Metadata } from 'next'
import { Mountain, Droplets, Route, AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { GenericAreaChart } from '@/components/charts/extra-charts'
import type { RiskLevel } from '@/types'

export const metadata: Metadata = {
  title: 'Landslide Prediction | VARUNA',
  description: 'Slope stability monitoring and rainfall-triggered landslide susceptibility.',
}

const SATURATION_SERIES = Array.from({ length: 14 }, (_, i) => ({
  day: `D-${13 - i}`,
  saturation: Math.min(98, Math.round(52 + i * 3.4 + Math.sin(i / 2) * 4)),
  threshold: 85,
}))

const SLOPE_ZONES: {
  zone: string
  corridor: string
  susceptibility: number
  saturation: number
  risk: RiskLevel
}[] = [
  { zone: 'Hanogi (NH-3)', corridor: 'Mandi–Kullu', susceptibility: 0.88, saturation: 94, risk: 'severe' },
  { zone: 'Kotrupi', corridor: 'Mandi–Pathankot', susceptibility: 0.81, saturation: 90, risk: 'severe' },
  { zone: 'Nigulsari (NH-5)', corridor: 'Rampur–Kinnaur', susceptibility: 0.72, saturation: 82, risk: 'high' },
  { zone: 'Banala', corridor: 'Kullu–Manali', susceptibility: 0.64, saturation: 78, risk: 'high' },
  { zone: 'Chamba bypass', corridor: 'Chamba–Bharmour', susceptibility: 0.48, saturation: 65, risk: 'moderate' },
  { zone: 'Solan section', corridor: 'Kalka–Shimla', susceptibility: 0.31, saturation: 52, risk: 'low' },
]

export default function LandslidePage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Landslide Prediction"
        description="Rainfall-triggered slope failure susceptibility combining antecedent moisture, slope, lithology and road-cut exposure."
      />

      <section aria-label="Slope indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Zones Monitored" value="142" icon={Mountain} sub="Across 12 districts" />
        <StatCard label="Critical Zones" value="2" icon={AlertTriangle} sub="Hanogi · Kotrupi" tone="danger" />
        <StatCard label="Antecedent Rain" value="248" unit="mm/7d" icon={Droplets} sub="Basin-weighted" tone="warning" />
        <StatCard label="Corridors at Risk" value="4" icon={Route} sub="NH-3, NH-5, NH-154, NH-205" tone="warning" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Soil Saturation vs Failure Threshold (14 days)</h2>
          <span className="text-[10px] font-mono text-muted-foreground">ERA5-Land soil moisture</span>
        </div>
        <GenericAreaChart
          data={SATURATION_SERIES}
          xKey="day"
          unit="%"
          series={[
            { key: 'saturation', name: 'Saturation' },
            { key: 'threshold', name: 'Failure threshold', color: 'oklch(0.64 0.2 25)', dashed: true },
          ]}
        />
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Slope Zone Watchlist</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">Zone</th>
                <th className="pb-2 pr-4 font-medium">Corridor</th>
                <th className="pb-2 pr-4 font-medium">Susceptibility</th>
                <th className="pb-2 pr-4 font-medium">Saturation</th>
                <th className="pb-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {SLOPE_ZONES.map((z) => (
                <tr key={z.zone} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{z.zone}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{z.corridor}</td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-24 rounded-full bg-secondary overflow-hidden">
                        <div
                          className={
                            z.susceptibility > 0.75
                              ? 'h-full bg-destructive'
                              : z.susceptibility > 0.55
                                ? 'h-full bg-warning'
                                : 'h-full bg-primary'
                          }
                          style={{ width: `${Math.round(z.susceptibility * 100)}%` }}
                        />
                      </div>
                      <span className="tabular-nums text-xs">{z.susceptibility.toFixed(2)}</span>
                    </div>
                  </td>
                  <td className="py-2.5 pr-4 tabular-nums">{z.saturation}%</td>
                  <td className="py-2.5"><RiskBadge risk={z.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

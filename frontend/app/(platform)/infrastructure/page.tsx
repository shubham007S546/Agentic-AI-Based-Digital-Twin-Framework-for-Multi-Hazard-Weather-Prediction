import type { Metadata } from 'next'
import { Building2, TriangleAlert, Route, Zap } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { INFRA_SUMMARY, CRITICAL_ASSETS } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Infrastructure | VARUNA',
  description: 'Critical infrastructure exposure — hospitals, bridges, highways and hydro assets.',
}

export default function InfrastructurePage() {
  const totalAtRisk = INFRA_SUMMARY.reduce((a, s) => a + s.atRisk, 0)
  const totalCritical = INFRA_SUMMARY.reduce((a, s) => a + s.critical, 0)
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Infrastructure Dashboard"
        description="GIS asset registry cross-referenced with live hazard layers — identifying hospitals, bridges, highways and hydro projects inside risk zones."
      />

      <section aria-label="Infrastructure indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Assets Registered" value="21.9" unit="K" icon={Building2} sub="OSM + state GIS registry" />
        <StatCard label="Assets at Risk" value={totalAtRisk.toLocaleString()} icon={TriangleAlert} sub="Inside active hazard zones" tone="warning" />
        <StatCard label="Critical Status" value={totalCritical} icon={Zap} sub="Immediate attention required" tone="danger" />
        <StatCard label="NH km Exposed" value="314" unit="km" icon={Route} sub="82 km critical (landslide)" tone="warning" />
      </section>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Asset Class Exposure</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {INFRA_SUMMARY.map((s) => {
            const pct = Math.round((s.atRisk / s.count) * 100)
            return (
              <div key={s.type} className="rounded-lg border border-border bg-secondary/40 p-4 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">{s.type}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">{s.count.toLocaleString()} total</span>
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-semibold tabular-nums">{s.atRisk}</span>
                  <span className="text-xs text-muted-foreground">at risk ({pct}%)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-secondary overflow-hidden">
                    <div className="h-full bg-warning" style={{ width: `${Math.min(100, pct * 4)}%` }} />
                  </div>
                  <span className="text-xs text-destructive tabular-nums">{s.critical} critical</span>
                </div>
              </div>
            )
          })}
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Critical Assets — Active Hazard Zones</h2>
          <span className="text-[10px] font-mono text-muted-foreground">refreshed with each model run</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">Asset</th>
                <th className="pb-2 pr-4 font-medium">Type</th>
                <th className="pb-2 pr-4 font-medium">District</th>
                <th className="pb-2 pr-4 font-medium">Hazard</th>
                <th className="pb-2 pr-4 font-medium">Distance</th>
                <th className="pb-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {CRITICAL_ASSETS.map((a) => (
                <tr key={a.id} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{a.name}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{a.type}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{a.district}</td>
                  <td className="py-2.5 pr-4">{a.hazard}</td>
                  <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">
                    {a.distanceM === 0 ? 'In zone' : `${a.distanceM} m`}
                  </td>
                  <td className="py-2.5">
                    <RiskBadge risk={a.risk} />
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

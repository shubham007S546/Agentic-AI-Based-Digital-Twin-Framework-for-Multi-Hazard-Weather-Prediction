import type { Metadata } from 'next'
import { Users, MapPin, ShieldAlert, Accessibility } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { GenericBarChart } from '@/components/charts/extra-charts'
import { DISTRICT_POPULATION, AGE_PYRAMID } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Population | VARUNA',
  description: 'District population exposure and vulnerability analytics for disaster planning.',
}

export default function PopulationPage() {
  const totalPop = DISTRICT_POPULATION.reduce((a, d) => a + d.population, 0)
  const totalExposed = DISTRICT_POPULATION.reduce((a, d) => a + d.exposed, 0)
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Population Dashboard"
        description="Village-level census data aggregated to districts — exposure and social vulnerability layers that convert hazard probability into human risk."
      />

      <section aria-label="Population indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="State Population" value={(totalPop / 1e6).toFixed(2)} unit="M" icon={Users} sub="Census projection 2026" />
        <StatCard label="Currently Exposed" value={(totalExposed / 1e3).toFixed(0)} unit="K" icon={ShieldAlert} sub="Within active hazard zones" tone="danger" />
        <StatCard label="Districts Monitored" value={DISTRICT_POPULATION.length} icon={MapPin} sub="All 12 districts covered" />
        <StatCard label="Vulnerable Groups" value="17.4" unit="%" icon={Accessibility} sub="Under 15 and over 60 in exposed zones" tone="warning" />
      </section>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">District Exposure Matrix</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">District</th>
                <th className="pb-2 pr-4 font-medium">Population</th>
                <th className="pb-2 pr-4 font-medium">Density /km²</th>
                <th className="pb-2 pr-4 font-medium">Exposed</th>
                <th className="pb-2 pr-4 font-medium">Vulnerability</th>
                <th className="pb-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {DISTRICT_POPULATION.map((d) => (
                <tr key={d.district} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{d.district}</td>
                  <td className="py-2.5 pr-4 tabular-nums">{d.population.toLocaleString()}</td>
                  <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">{d.density}</td>
                  <td className="py-2.5 pr-4 tabular-nums">{d.exposed.toLocaleString()}</td>
                  <td className="py-2.5 pr-4">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-20 rounded-full bg-secondary overflow-hidden">
                        <div
                          className={d.vulnerability > 0.65 ? 'h-full bg-destructive' : d.vulnerability > 0.45 ? 'h-full bg-warning' : 'h-full bg-primary'}
                          style={{ width: `${d.vulnerability * 100}%` }}
                        />
                      </div>
                      <span className="tabular-nums text-xs">{d.vulnerability}</span>
                    </div>
                  </td>
                  <td className="py-2.5">
                    <RiskBadge risk={d.risk} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Demographic Structure — Exposed Population</h2>
          <span className="text-[10px] font-mono text-muted-foreground">% share by age group</span>
        </div>
        <GenericBarChart
          data={AGE_PYRAMID}
          xKey="group"
          unit="%"
          series={[
            { key: 'male', name: 'Male' },
            { key: 'female', name: 'Female' },
          ]}
        />
        <p className="text-xs text-muted-foreground mt-3 text-pretty">
          Age structure of populations inside active hazard zones. Evacuation planning weights
          the under-15 and over-60 cohorts, which require assisted movement and longer lead times.
        </p>
      </GlassCard>
    </div>
  )
}

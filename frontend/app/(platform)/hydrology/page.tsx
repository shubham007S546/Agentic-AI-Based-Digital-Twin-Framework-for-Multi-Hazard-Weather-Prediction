import type { Metadata } from 'next'
import { Droplets, Waves, Gauge, Snowflake } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { GenericAreaChart, GenericBarChart } from '@/components/charts/extra-charts'
import { RIVER_GAUGES } from '@/lib/mock/data'
import { DISCHARGE_SERIES, CATCHMENTS, GROUNDWATER_LEVELS } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Hydrology | VARUNA',
  description: 'Basin-scale river discharge, catchment state and groundwater analytics.',
}

export default function HydrologyPage() {
  const rising = RIVER_GAUGES.filter((g) => g.trend === 'rising').length
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Hydrology Dashboard"
        description="Basin-scale discharge monitoring, catchment saturation state and groundwater dynamics across the five major Himachal river systems."
      />

      <section aria-label="Hydrology indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active Gauges" value={RIVER_GAUGES.length * 10} icon={Gauge} sub="CWC + state telemetry" />
        <StatCard label="Rivers Rising" value={rising} icon={Waves} sub={`of ${RIVER_GAUGES.length} monitored stations`} tone="warning" />
        <StatCard label="Basin Soil Moisture" value="86" unit="%" icon={Droplets} sub="Beas catchment mean, top 1m" tone="danger" />
        <StatCard label="Snow Cover" value="34" unit="%" icon={Snowflake} sub="Beas basin, MODIS 8-day" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">River Discharge — 30 Day Analytics</h2>
          <span className="text-[10px] font-mono text-muted-foreground">m³/s · daily mean</span>
        </div>
        <GenericAreaChart
          data={DISCHARGE_SERIES}
          xKey="day"
          unit=""
          interval={4}
          height={300}
          series={[
            { key: 'beas', name: 'Beas (Pandoh)' },
            { key: 'sutlej', name: 'Sutlej (Rampur)' },
            { key: 'ravi', name: 'Ravi (Chamba)' },
          ]}
        />
      </GlassCard>

      <div className="grid lg:grid-cols-2 gap-6">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Catchment State</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-border">
                  <th className="pb-2 pr-4 font-medium">Basin</th>
                  <th className="pb-2 pr-4 font-medium">Area km²</th>
                  <th className="pb-2 pr-4 font-medium">Soil Moist.</th>
                  <th className="pb-2 pr-4 font-medium">Runoff Idx</th>
                  <th className="pb-2 font-medium">Risk</th>
                </tr>
              </thead>
              <tbody>
                {CATCHMENTS.map((c) => (
                  <tr key={c.basin} className="border-b border-border/50 last:border-0">
                    <td className="py-2.5 pr-4 font-medium">{c.basin}</td>
                    <td className="py-2.5 pr-4 tabular-nums text-muted-foreground">{c.area.toLocaleString()}</td>
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 rounded-full bg-secondary overflow-hidden">
                          <div
                            className={c.soilMoisture > 80 ? 'h-full bg-destructive' : c.soilMoisture > 65 ? 'h-full bg-warning' : 'h-full bg-primary'}
                            style={{ width: `${c.soilMoisture}%` }}
                          />
                        </div>
                        <span className="tabular-nums text-xs">{c.soilMoisture}%</span>
                      </div>
                    </td>
                    <td className="py-2.5 pr-4 tabular-nums">{c.runoffIndex}</td>
                    <td className="py-2.5">
                      <RiskBadge risk={c.risk} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Groundwater Depth — Annual Cycle</h2>
            <span className="text-[10px] font-mono text-muted-foreground">m below ground</span>
          </div>
          <GenericBarChart
            data={GROUNDWATER_LEVELS}
            xKey="month"
            unit="m"
            series={[{ key: 'level', name: 'Depth to water table' }]}
          />
          <p className="text-xs text-muted-foreground mt-3 text-pretty">
            Monsoon recharge (Jul–Sep) lifts the water table by ~5m relative to the pre-monsoon
            low. Shallow tables during active spells amplify runoff generation and flash-flood
            response in lower catchments.
          </p>
        </GlassCard>
      </div>
    </div>
  )
}

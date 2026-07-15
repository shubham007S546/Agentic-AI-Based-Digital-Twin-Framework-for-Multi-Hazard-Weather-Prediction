import type { Metadata } from 'next'
import { Leaf, Trees, Sprout, ThermometerSun } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericAreaChart } from '@/components/charts/extra-charts'
import { NDVI_SERIES, LST_SERIES, LAND_COVER } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Vegetation | VARUNA',
  description: 'NDVI, EVI and MODIS land-surface analytics for vegetation health monitoring.',
}

export default function VegetationPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Vegetation Dashboard"
        description="NDVI/EVI vegetation indices, MODIS land-surface temperature and land-cover composition — key covariates for runoff and slope-stability modelling."
      />

      <section aria-label="Vegetation indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Current NDVI" value="0.58" icon={Leaf} sub="State mean, 16-day composite" tone="success" />
        <StatCard label="Forest Cover" value="41.6" unit="%" icon={Trees} sub="Dense + open forest classes" />
        <StatCard label="NDVI Anomaly" value="+0.04" icon={Sprout} sub="vs 10-year climatology" tone="success" />
        <StatCard label="Day LST" value="26.4" unit="°C" icon={ThermometerSun} sub="MODIS Terra, last composite" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">NDVI Dashboard — Annual Vegetation Cycle</h2>
          <span className="text-[10px] font-mono text-muted-foreground">MODIS 16-day · 24 composites</span>
        </div>
        <GenericAreaChart
          data={NDVI_SERIES}
          xKey="period"
          interval={2}
          height={280}
          series={[
            { key: 'ndvi', name: 'NDVI' },
            { key: 'evi', name: 'EVI' },
          ]}
        />
        <p className="text-xs text-muted-foreground mt-3 text-pretty">
          Peak greenness occurs in composites P13–P16 (Jul–Aug), lagging monsoon onset by roughly
          three weeks. Sharp NDVI drawdowns outside this window flag drought stress or disturbance.
        </p>
      </GlassCard>

      <div className="grid lg:grid-cols-2 gap-6">
        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">MODIS Land Surface Temperature</h2>
            <span className="text-[10px] font-mono text-muted-foreground">Terra day / night · °C</span>
          </div>
          <GenericAreaChart
            data={LST_SERIES}
            xKey="period"
            unit="°"
            interval={2}
            series={[
              { key: 'day', name: 'Day LST' },
              { key: 'night', name: 'Night LST' },
            ]}
          />
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Land Cover Composition</h2>
          <ul className="flex flex-col gap-2.5">
            {LAND_COVER.map((lc) => (
              <li key={lc.class} className="flex items-center gap-3">
                <span className="w-28 shrink-0 text-xs text-muted-foreground">{lc.class}</span>
                <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${Math.min(100, lc.pct * 3)}%` }} />
                </div>
                <span className="w-12 text-right text-xs tabular-nums">{lc.pct}%</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground mt-4 text-pretty">
            Derived from Sentinel-2 10m classification, cross-validated against MODIS MCD12Q1.
            Built-up expansion in valley floors (+0.4%/yr) increases exposure within flood plains.
          </p>
        </GlassCard>
      </div>
    </div>
  )
}

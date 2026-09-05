import type { Metadata } from 'next'
import { Layers, Mountain, Compass, TriangleAlert } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericAreaChart, GenericBarChart } from '@/components/charts/extra-charts'
import {
  ELEVATION_PROFILE,
  ELEVATION_BANDS,
  SLOPE_DISTRIBUTION,
  ASPECT_DISTRIBUTION,
} from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Terrain Analysis | VARUNA',
  description: 'DEM visualization, slope stability and aspect analysis from 30m SRTM/ALOS data.',
}

const STABILITY_CLASS: Record<string, string> = {
  Stable: 'text-success',
  Marginal: 'text-warning',
  Unstable: 'text-warning',
  Critical: 'text-destructive',
}

export default function TerrainPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Terrain Analysis"
        description="DEM-derived elevation, slope and aspect analytics from 30m SRTM/ALOS data — the static backbone of landslide susceptibility and runoff models."
      />

      <section aria-label="Terrain indicators" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="DEM Resolution" value="30" unit="m" icon={Layers} sub="SRTM v3 + ALOS PALSAR fused" />
        <StatCard label="Elevation Range" value="320–6816" unit="m" icon={Mountain} sub="Una lowlands to Shilla peak" />
        <StatCard label="Mean Slope" value="24.6" unit="°" icon={Compass} sub="State-wide DEM derivative" />
        <StatCard label="Critical Slope Area" value="15" unit="%" icon={TriangleAlert} sub="Slopes above 40°" tone="warning" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">DEM Elevation Profile — Beas Valley Transect</h2>
          <span className="text-[10px] font-mono text-muted-foreground">Mandi → Rohtang · 160 km</span>
        </div>
        <GenericAreaChart
          data={ELEVATION_PROFILE}
          xKey="km"
          unit="m"
          interval={4}
          height={280}
          series={[{ key: 'elevation', name: 'Elevation' }]}
        />
      </GlassCard>

      <div className="grid lg:grid-cols-2 gap-6">
        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Slope Analysis</h2>
            <span className="text-[10px] font-mono text-muted-foreground">% of state area</span>
          </div>
          <GenericBarChart
            data={SLOPE_DISTRIBUTION}
            xKey="range"
            unit="%"
            series={[{ key: 'areaPct', name: 'Area share' }]}
          />
          <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
            {SLOPE_DISTRIBUTION.map((s) => (
              <li key={s.range} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{s.range}</span>
                <span className={STABILITY_CLASS[s.stability]}>{s.stability}</span>
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-medium">Aspect Analysis</h2>
            <span className="text-[10px] font-mono text-muted-foreground">wetness index by facing</span>
          </div>
          <GenericBarChart
            data={ASPECT_DISTRIBUTION}
            xKey="aspect"
            series={[
              { key: 'areaPct', name: 'Area %' },
              { key: 'wetness', name: 'Wetness index' },
            ]}
          />
          <p className="text-xs text-muted-foreground mt-3 text-pretty">
            North and northeast facing slopes retain higher soil moisture (wetness index
            0.66–0.72), correlating with elevated landslide frequency during sustained monsoon
            saturation.
          </p>
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Landslide Incidence by Elevation Band</h2>
          <span className="text-[10px] font-mono text-muted-foreground">events 2015–2025 · HPSDMA</span>
        </div>
        <GenericBarChart
          data={ELEVATION_BANDS}
          xKey="band"
          series={[
            { key: 'areaPct', name: 'Area %' },
            { key: 'landslides', name: 'Recorded slides' },
          ]}
        />
      </GlassCard>
    </div>
  )
}

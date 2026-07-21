import type { Metadata } from 'next'
import { CloudRain, Droplets, Wind } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { GlassCard } from '@/components/shared/glass-card'
import { ForecastTempChart, ForecastRainChart } from '@/components/charts/extra-charts'
import { PredictionTimelineChart } from '@/components/charts/charts'
import { FORECAST_7D } from '@/lib/mock/data'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Forecast | VARUNA',
  description: '7-day and 48-hour probabilistic forecasts for Himachal Pradesh.',
}

export default function ForecastPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Forecast"
        description="Multi-horizon forecasts blending numerical weather prediction with AI models. Confidence bands from ensemble spread."
      />

      <section aria-label="7 day forecast" className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-7 gap-3">
        {FORECAST_7D.map((d) => (
          <GlassCard
            key={d.date}
            className={cn(
              'p-4 flex flex-col gap-2',
              d.rainProbability > 85 && 'border-destructive/40',
            )}
          >
            <span className="text-xs font-medium text-muted-foreground">{d.day}</span>
            <span className="text-lg font-semibold tabular-nums">
              {d.tempMax}° <span className="text-sm text-muted-foreground font-normal">/ {d.tempMin}°</span>
            </span>
            <span className="text-xs text-pretty">{d.condition}</span>
            <div className="flex flex-col gap-1 mt-1 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <CloudRain className="size-3 text-primary" aria-hidden="true" />
                {d.rainfall} mm · {d.rainProbability}%
              </span>
              <span className="flex items-center gap-1.5">
                <Droplets className="size-3 text-primary" aria-hidden="true" />
                {d.humidity}% RH
              </span>
              <span className="flex items-center gap-1.5">
                <Wind className="size-3 text-primary" aria-hidden="true" />
                {d.windSpeed} km/h
              </span>
            </div>
          </GlassCard>
        ))}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Temperature Range (7 days)</h2>
          <ForecastTempChart />
        </GlassCard>
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Daily Rainfall Accumulation</h2>
          <ForecastRainChart />
        </GlassCard>
      </div>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">48-hour Probabilistic Rainfall — TFT Ensemble</h2>
          <span className="text-[10px] font-mono text-muted-foreground">Temporal Fusion Transformer</span>
        </div>
        <PredictionTimelineChart />
      </GlassCard>
    </div>
  )
}

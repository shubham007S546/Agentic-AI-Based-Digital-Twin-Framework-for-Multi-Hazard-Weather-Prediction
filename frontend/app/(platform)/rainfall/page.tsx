import type { Metadata } from 'next'
import { CloudRain, Timer, Target, Layers } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { HourlyRainfallChart, MonthlyRainfallChart, PredictionTimelineChart } from '@/components/charts/charts'
import { HAZARD_STATIONS } from '@/lib/mock/data'
import { getRainfallPredictions } from '@/lib/api/predictions'
import { LiveDistrictRisk } from '@/components/predictions/live-district-risk'

export const metadata: Metadata = {
  title: 'Rainfall Prediction | VARUNA',
  description: 'AI-driven rainfall nowcasting and multi-horizon prediction.',
}

export default async function RainfallPage() {
  const predictions = await getRainfallPredictions()

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Rainfall Prediction"
        description="Nowcasting and multi-horizon rainfall prediction fusing OpenWeather, Open-Meteo, ERA5 and station data through gradient-boosted and deep sequence models."
      />

      <section aria-label="Model summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active Model" value="LSTM v1" icon={Layers} sub="Deep Learning · Live" />
        <StatCard label="Lead Time" value="72" unit="h" icon={Timer} sub="Max forecast horizon" />
        <StatCard label="MAE" value="3.12" unit="mm" icon={Target} sub="Validation window" tone="success" />
        <StatCard label="Districts Live" value={String(predictions.length || 5)} icon={CloudRain} sub="Chamba, Mandi, Kullu..." tone="warning" />
      </section>

      <LiveDistrictRisk hazard="rainfall" initialData={predictions} />

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Nowcast — Observed vs Predicted (24h)</h2>
          <span className="text-[10px] font-mono text-muted-foreground">10-min cadence</span>
        </div>
        <HourlyRainfallChart />
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">48-hour Probabilistic Prediction</h2>
          <span className="text-[10px] font-mono text-muted-foreground">TFT · 90% CI</span>
        </div>
        <PredictionTimelineChart />
      </GlassCard>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Seasonal Context — Monthly vs Normal</h2>
          <MonthlyRainfallChart />
        </GlassCard>
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Station Rainfall Risk</h2>
          <ul className="flex flex-col gap-2.5">
            {HAZARD_STATIONS.slice(0, 8).map((st) => (
              <li key={st.id} className="flex items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-medium">{st.name}</span>
                    <span className="tabular-nums text-muted-foreground">{st.metric} mm / 24h</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
                    <div
                      className={
                        st.probability > 75
                          ? 'h-full bg-destructive'
                          : st.probability > 50
                            ? 'h-full bg-warning'
                            : 'h-full bg-primary'
                      }
                      style={{ width: `${st.probability}%` }}
                    />
                  </div>
                </div>
                <RiskBadge risk={st.risk} />
              </li>
            ))}
          </ul>
        </GlassCard>
      </div>
    </div>
  )
}

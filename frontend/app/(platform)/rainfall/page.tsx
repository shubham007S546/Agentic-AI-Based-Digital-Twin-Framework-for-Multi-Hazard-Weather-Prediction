import type { Metadata } from 'next'
import { CloudRain, Timer, Target, Layers } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { HourlyRainfallChart, MonthlyRainfallChart, PredictionTimelineChart } from '@/components/charts/charts'
import { HAZARD_STATIONS } from '@/lib/mock/data'

export const metadata: Metadata = {
  title: 'Rainfall Prediction | VARUNA',
  description: 'AI-driven rainfall nowcasting and multi-horizon prediction.',
}

export default function RainfallPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Rainfall Prediction"
        description="Nowcasting and multi-horizon rainfall prediction fusing GPM IMERG, ERA5 and station data through gradient-boosted and deep sequence models."
      />

      <section aria-label="Model summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active Model" value="XGBoost" icon={Layers} sub="Champion · R² 0.82" />
        <StatCard label="Lead Time" value="72" unit="h" icon={Timer} sub="Max forecast horizon" />
        <StatCard label="MAE" value="3.12" unit="mm" icon={Target} sub="Validation window" tone="success" />
        <StatCard label="Next 6h Peak" value="18.4" unit="mm/h" icon={CloudRain} sub="Upper Beas basin" tone="warning" />
      </section>

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

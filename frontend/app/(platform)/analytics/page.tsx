import type { Metadata } from 'next'
import { BarChart3, Trophy, Target, Cpu } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { TrainingHistoryChart } from '@/components/charts/charts'
import { ModelComparisonExplorer } from '@/components/analytics/model-comparison'
import { MODEL_METRICS } from '@/lib/mock/data'

export const metadata: Metadata = {
  title: 'Model Comparison | VARUNA',
  description: 'Benchmark classical ML, deep learning and transformer models across accuracy and efficiency metrics.',
}

export default function AnalyticsPage() {
  const trained = MODEL_METRICS.filter((m) => m.status === 'trained').length
  const training = MODEL_METRICS.filter((m) => m.status === 'training').length
  const bestMae = Math.min(...MODEL_METRICS.filter((m) => m.status === 'trained').map((m) => m.mae))

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Model Comparison"
        description="Side-by-side benchmarking of the full model zoo — six classical ML models, four deep sequence models and four transformer architectures."
      />

      <section aria-label="Model zoo summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Models Tracked" value={MODEL_METRICS.length} icon={BarChart3} sub={`${trained} trained · ${training} training`} />
        <StatCard label="Champion" value="XGBoost" icon={Trophy} sub="Best deployed MAE / latency trade-off" tone="success" />
        <StatCard label="Best MAE" value={bestMae.toFixed(2)} unit="mm" icon={Target} sub="Among trained models" />
        <StatCard label="Fastest Inference" value="0.2" unit="ms" icon={Cpu} sub="Linear Regression baseline" />
      </section>

      <ModelComparisonExplorer />

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Active Training — LSTM Loss Curves</h2>
          <span className="text-[10px] font-mono text-muted-foreground">gpu-node-02 · epoch 34/40</span>
        </div>
        <TrainingHistoryChart />
      </GlassCard>
    </div>
  )
}

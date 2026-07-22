import type { Metadata } from 'next'
import { BarChart3, Trophy, Target, Cpu } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { TrainingHistoryChart } from '@/components/charts/charts'
import { ModelComparisonExplorer } from '@/components/analytics/model-comparison'
import { getModelBenchmark } from '@/lib/api/models'

export const metadata: Metadata = {
  title: 'Model Comparison | VARUNA',
  description: 'Benchmark classical ML, deep learning and transformer models across accuracy and efficiency metrics.',
}

export default async function AnalyticsPage() {
  const benchmark = await getModelBenchmark()
  const {
    models,
    champion,
    best_mae: bestMae,
    fastest_inference: fastestInf,
    total_tracked: totalTracked,
    trained_count: trainedCount,
    training_count: trainingCount,
  } = benchmark

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Model Comparison"
        description="Side-by-side benchmarking of the full model zoo — dynamically updated as new models are trained, registered, or deployed."
      />

      <section aria-label="Model zoo summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Models Tracked"
          value={totalTracked}
          icon={BarChart3}
          sub={`${trainedCount} trained · ${trainingCount} training`}
        />
        <StatCard
          label="Champion Model"
          value={champion}
          icon={Trophy}
          sub="Dynamically selected by best MAE / accuracy"
          tone="success"
        />
        <StatCard label="Best MAE" value={bestMae.toFixed(3)} unit="mm" icon={Target} sub="Among trained models" />
        <StatCard label="Fastest Inference" value={fastestInf.toFixed(1)} unit="ms" icon={Cpu} sub="Baseline latency" />
      </section>

      <ModelComparisonExplorer initialModels={models} champion={champion} />

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Active Training — Sequence Model Loss Curves</h2>
          <span className="text-[10px] font-mono text-muted-foreground">gpu-node-02 · live metrics</span>
        </div>
        <TrainingHistoryChart />
      </GlassCard>
    </div>
  )
}

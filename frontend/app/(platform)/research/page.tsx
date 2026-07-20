import type { Metadata } from 'next'
import { FlaskConical, GitBranch, Database, FileText, CheckCircle2, CircleDot, Circle } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { TrainingHistoryChart } from '@/components/charts/charts'
import { PIPELINE_STAGES } from '@/lib/mock/data'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Research Dashboard | VARUNA',
  description: 'Research pipeline progress, experiment tracking and publication milestones.',
}

const EXPERIMENTS = [
  { id: 'exp-128', name: 'XGBoost + monsoon-2026 features', dataset: 'master-v14', metric: 'MAE 3.12', delta: '-0.06', status: 'complete', date: '14 Jul 2026' },
  { id: 'exp-127', name: 'LSTM 2-layer, seq len 48', dataset: 'master-v14', metric: 'val loss 0.412', delta: '-0.031', status: 'running', date: '15 Jul 2026' },
  { id: 'exp-126', name: 'GRU + terrain embedding', dataset: 'master-v14', metric: 'val loss 0.428', delta: '-0.012', status: 'running', date: '15 Jul 2026' },
  { id: 'exp-125', name: 'LightGBM DART, 4k trees', dataset: 'master-v13', metric: 'MAE 3.18', delta: '+0.02', status: 'complete', date: '12 Jul 2026' },
  { id: 'exp-124', name: 'RF depth sweep (8–32)', dataset: 'master-v13', metric: 'MAE 3.44', delta: '0.00', status: 'complete', date: '11 Jul 2026' },
  { id: 'exp-123', name: 'Feature ablation — remove NDVI', dataset: 'master-v13', metric: 'MAE 3.21', delta: '+0.09', status: 'complete', date: '10 Jul 2026' },
]

const MILESTONES = [
  { title: 'Conference paper — cloudburst nowcasting', venue: 'Under review', date: 'Aug 2026' },
  { title: 'Master dataset v14 release notes', venue: 'Internal', date: 'Jul 2026' },
  { title: 'Benchmark report — classical vs deep models', venue: 'Published', date: 'Jun 2026' },
  { title: 'Data descriptor — Himachal hazard archive', venue: 'Draft', date: 'Sep 2026' },
]

export default function ResearchPage() {
  const complete = PIPELINE_STAGES.filter((s) => s.status === 'complete').length

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Research Dashboard"
        description="End-to-end research pipeline tracking — from dataset collection through transformer benchmarking to the operational early-warning platform."
      />

      <section aria-label="Research summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Pipeline Progress" value={`${complete}/${PIPELINE_STAGES.length}`} icon={GitBranch} sub="Stages complete" />
        <StatCard label="Experiments" value={128} icon={FlaskConical} sub="Tracked runs this quarter" />
        <StatCard label="Master Dataset" value="v14" icon={Database} sub="312 features · 8 sources" tone="success" />
        <StatCard label="Publications" value={4} icon={FileText} sub="1 published · 1 in review" />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <GlassCard className="p-5 xl:col-span-2">
          <h2 className="text-sm font-medium mb-4">Research Pipeline</h2>
          <ol className="flex flex-col">
            {PIPELINE_STAGES.map((stage, i) => (
              <li key={stage.name} className="flex gap-3">
                <div className="flex flex-col items-center">
                  {stage.status === 'complete' ? (
                    <CheckCircle2 className="size-4 text-success shrink-0" aria-hidden="true" />
                  ) : stage.status === 'active' ? (
                    <CircleDot className="size-4 text-primary shrink-0" aria-hidden="true" />
                  ) : (
                    <Circle className="size-4 text-muted-foreground/40 shrink-0" aria-hidden="true" />
                  )}
                  {i < PIPELINE_STAGES.length - 1 && (
                    <span
                      className={cn(
                        'w-px flex-1 my-1',
                        stage.status === 'complete' ? 'bg-success/40' : 'bg-border',
                      )}
                    />
                  )}
                </div>
                <div className="pb-4 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium">{stage.name}</span>
                    {stage.status === 'active' && (
                      <span className="rounded-full bg-primary/15 text-primary border border-primary/30 px-1.5 py-0.5 text-[10px]">
                        active
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-0.5 text-pretty">{stage.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </GlassCard>

        <div className="xl:col-span-3 flex flex-col gap-4">
          <GlassCard className="p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium">Current Training Run — exp-127</h2>
              <span className="text-[10px] font-mono text-muted-foreground">LSTM · seq 48 · lr 3e-4</span>
            </div>
            <TrainingHistoryChart />
          </GlassCard>

          <GlassCard className="p-0 overflow-hidden">
            <h2 className="text-sm font-medium p-5 pb-3">Experiment Log</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-y border-border text-muted-foreground">
                    <th className="text-left font-medium px-5 py-2.5" scope="col">Run</th>
                    <th className="text-left font-medium px-3 py-2.5" scope="col">Experiment</th>
                    <th className="text-left font-medium px-3 py-2.5" scope="col">Dataset</th>
                    <th className="text-left font-medium px-3 py-2.5" scope="col">Best Metric</th>
                    <th className="text-right font-medium px-3 py-2.5" scope="col">Δ vs prev</th>
                    <th className="text-left font-medium px-5 py-2.5" scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {EXPERIMENTS.map((e) => (
                    <tr key={e.id} className="border-b border-border/50 hover:bg-secondary/40 transition-colors">
                      <td className="px-5 py-2.5 font-mono text-muted-foreground">{e.id}</td>
                      <td className="px-3 py-2.5 font-medium">{e.name}</td>
                      <td className="px-3 py-2.5 font-mono text-muted-foreground">{e.dataset}</td>
                      <td className="px-3 py-2.5 font-mono tabular-nums">{e.metric}</td>
                      <td
                        className={cn(
                          'px-3 py-2.5 text-right font-mono tabular-nums',
                          e.delta.startsWith('-') ? 'text-success' : e.delta.startsWith('+') ? 'text-destructive' : 'text-muted-foreground',
                        )}
                      >
                        {e.delta}
                      </td>
                      <td className="px-5 py-2.5">
                        <span
                          className={cn(
                            'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize',
                            e.status === 'running'
                              ? 'bg-warning/15 text-warning border-warning/30'
                              : 'bg-success/15 text-success border-success/30',
                          )}
                        >
                          {e.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          <GlassCard className="p-5">
            <h2 className="text-sm font-medium mb-3">Publication Milestones</h2>
            <ul className="flex flex-col gap-2.5">
              {MILESTONES.map((m) => (
                <li key={m.title} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-xs font-medium block truncate">{m.title}</span>
                    <span className="text-[10px] text-muted-foreground">{m.venue}</span>
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground shrink-0">{m.date}</span>
                </li>
              ))}
            </ul>
          </GlassCard>
        </div>
      </div>
    </div>
  )
}

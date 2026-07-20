'use client'

import { useMemo, useState } from 'react'
import { GlassCard } from '@/components/shared/glass-card'
import { ModelCompareChart } from '@/components/charts/charts'
import { MODEL_METRICS } from '@/lib/mock/data'
import { cn } from '@/lib/utils'

type MetricKey = 'mae' | 'rmse' | 'r2' | 'f1'
type CategoryKey = 'all' | 'ml' | 'dl' | 'transformer'

const METRIC_LABELS: Record<MetricKey, string> = {
  mae: 'MAE (mm) — lower is better',
  rmse: 'RMSE (mm) — lower is better',
  r2: 'R² — higher is better',
  f1: 'F1 score — higher is better',
}

const CATEGORY_LABELS: Record<CategoryKey, string> = {
  all: 'All',
  ml: 'Classical ML',
  dl: 'Deep Learning',
  transformer: 'Transformers',
}

const STATUS_STYLES: Record<string, string> = {
  trained: 'bg-success/15 text-success border-success/30',
  training: 'bg-warning/15 text-warning border-warning/30',
  planned: 'bg-secondary text-muted-foreground border-border',
}

export function ModelComparisonExplorer() {
  const [metric, setMetric] = useState<MetricKey>('mae')
  const [category, setCategory] = useState<CategoryKey>('all')

  const filtered = useMemo(
    () => MODEL_METRICS.filter((m) => category === 'all' || m.category === category),
    [category],
  )

  const chartData = useMemo(
    () =>
      [...filtered]
        .sort((a, b) => (metric === 'r2' || metric === 'f1' ? b[metric] - a[metric] : a[metric] - b[metric]))
        .map((m) => ({ name: m.name, value: m[metric] })),
    [filtered, metric],
  )

  return (
    <div className="flex flex-col gap-4">
      <GlassCard className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <h2 className="text-sm font-medium">Benchmark — {METRIC_LABELS[metric]}</h2>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg bg-secondary p-0.5" role="tablist" aria-label="Metric">
              {(Object.keys(METRIC_LABELS) as MetricKey[]).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={metric === m}
                  onClick={() => setMetric(m)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-xs font-medium uppercase transition-colors',
                    metric === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1 rounded-lg bg-secondary p-0.5" role="tablist" aria-label="Model family">
              {(Object.keys(CATEGORY_LABELS) as CategoryKey[]).map((c) => (
                <button
                  key={c}
                  role="tab"
                  aria-selected={category === c}
                  onClick={() => setCategory(c)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                    category === c
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {CATEGORY_LABELS[c]}
                </button>
              ))}
            </div>
          </div>
        </div>
        <ModelCompareChart data={chartData} metric={metric} label={METRIC_LABELS[metric]} />
      </GlassCard>

      <GlassCard className="p-0 overflow-hidden">
        <div className="p-5 pb-3">
          <h2 className="text-sm font-medium">Full Metric Matrix</h2>
          <p className="text-xs text-muted-foreground mt-1">
            {filtered.length} models · validation window Jun–Jul 2026 · rainfall regression + hazard classification
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-y border-border text-muted-foreground">
                <th className="text-left font-medium px-5 py-2.5" scope="col">Model</th>
                <th className="text-left font-medium px-3 py-2.5" scope="col">Family</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">MAE</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">RMSE</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">R²</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">F1</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">MCC</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">Infer (ms)</th>
                <th className="text-right font-medium px-3 py-2.5" scope="col">Params</th>
                <th className="text-left font-medium px-5 py-2.5" scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => (
                <tr key={m.name} className="border-b border-border/50 hover:bg-secondary/40 transition-colors">
                  <td className="px-5 py-2.5 font-medium whitespace-nowrap">
                    {m.name}
                    {m.name === 'XGBoost' && (
                      <span className="ml-2 rounded-full bg-primary/15 text-primary border border-primary/30 px-1.5 py-0.5 text-[10px]">
                        champion
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground uppercase">{m.category}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.mae.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.rmse.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.r2.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.f1.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.mcc.toFixed(2)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.inferenceMs.toFixed(1)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{m.params}</td>
                  <td className="px-5 py-2.5">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize',
                        STATUS_STYLES[m.status],
                      )}
                    >
                      {m.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

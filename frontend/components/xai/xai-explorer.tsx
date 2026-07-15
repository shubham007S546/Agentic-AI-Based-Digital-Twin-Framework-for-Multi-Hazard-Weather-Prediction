'use client'

import { useState } from 'react'
import { Brain, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { FeatureImportanceChart } from '@/components/charts/charts'
import { cn } from '@/lib/utils'

const LOCAL_EXPLANATION = [
  { feature: 'Rainfall (t-1h)', value: '14.2 mm', contribution: 0.28 },
  { feature: 'CAPE', value: '2,840 J/kg', contribution: 0.21 },
  { feature: 'GPM Precipitation', value: '11.8 mm/h', contribution: 0.17 },
  { feature: 'Relative Humidity', value: '96%', contribution: 0.11 },
  { feature: 'Cloud Cover (High)', value: '92%', contribution: 0.08 },
  { feature: 'Surface Pressure Δ', value: '-4.2 hPa', contribution: 0.06 },
  { feature: 'Elevation', value: '2,050 m', contribution: 0.04 },
  { feature: 'NDVI', value: '0.61', contribution: -0.03 },
  { feature: 'Soil Moisture', value: '0.42 m³/m³', contribution: -0.05 },
  { feature: 'Wind Speed 850hPa', value: '9.4 m/s', contribution: 0.04 },
]

const ATTENTION_STEPS = ['t-12h', 't-10h', 't-8h', 't-6h', 't-4h', 't-2h', 't-1h', 't']
const ATTENTION_FEATURES = ['Rainfall', 'CAPE', 'Humidity', 'Pressure', 'Cloud Top', 'Wind']

// Deterministic pseudo-attention weights (no Math.random to avoid hydration mismatch)
function attentionWeight(f: number, t: number) {
  const base = Math.sin(f * 1.7 + t * 0.9) * 0.5 + 0.5
  const recency = t / (ATTENTION_STEPS.length - 1)
  return Math.min(1, base * 0.45 + recency * 0.55 * (f === 0 || f === 1 ? 1 : 0.7))
}

export function GlobalImportancePanel() {
  const [metric, setMetric] = useState<'shap' | 'importance'>('shap')
  return (
    <GlassCard className="p-5">
      <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
        <h2 className="text-sm font-medium">Global Feature Attribution</h2>
        <div className="flex items-center gap-1 rounded-lg bg-secondary p-0.5" role="tablist" aria-label="Attribution metric">
          {(['shap', 'importance'] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={metric === m}
              onClick={() => setMetric(m)}
              className={cn(
                'px-3 py-1 rounded-md text-xs font-medium transition-colors',
                metric === m ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {m === 'shap' ? 'Mean |SHAP|' : 'Gain Importance'}
            </button>
          ))}
        </div>
      </div>
      <FeatureImportanceChart metric={metric} />
      <p className="text-xs text-muted-foreground mt-3 text-pretty">
        {metric === 'shap'
          ? 'Mean absolute SHAP values computed over the 2026 monsoon validation window (n = 48,200 samples) for the champion XGBoost rainfall model.'
          : 'Gain-based split importance from the trained gradient-boosted ensemble. Correlated features may share credit; prefer SHAP for attribution.'}
      </p>
    </GlassCard>
  )
}

export function LocalExplanationPanel() {
  const maxAbs = Math.max(...LOCAL_EXPLANATION.map((d) => Math.abs(d.contribution)))
  return (
    <GlassCard className="p-5">
      <div className="flex items-start justify-between gap-2 mb-1">
        <h2 className="text-sm font-medium">Local Explanation — Single Prediction</h2>
        <span className="text-[10px] font-mono text-muted-foreground shrink-0">SHAP force decomposition</span>
      </div>
      <p className="text-xs text-muted-foreground mb-4 text-pretty">
        Cloudburst probability <span className="text-destructive font-semibold">91%</span> for Kullu (upper Beas
        basin), issued 06:40 IST. Base rate 12% shifted by the contributions below.
      </p>
      <ul className="flex flex-col gap-2.5">
        {LOCAL_EXPLANATION.map((d) => {
          const positive = d.contribution >= 0
          return (
            <li key={d.feature} className="flex items-center gap-3">
              <div className="w-36 shrink-0">
                <span className="text-xs font-medium block truncate">{d.feature}</span>
                <span className="text-[10px] font-mono text-muted-foreground">{d.value}</span>
              </div>
              <div className="flex-1 h-2 rounded-full bg-secondary overflow-hidden flex">
                <div className="w-1/2 flex justify-end">
                  {!positive && (
                    <div
                      className="h-full bg-success rounded-l-full"
                      style={{ width: `${(Math.abs(d.contribution) / maxAbs) * 100}%` }}
                    />
                  )}
                </div>
                <div className="w-1/2">
                  {positive && (
                    <div
                      className="h-full bg-destructive rounded-r-full"
                      style={{ width: `${(d.contribution / maxAbs) * 100}%` }}
                    />
                  )}
                </div>
              </div>
              <span
                className={cn(
                  'w-14 shrink-0 text-right text-xs font-mono tabular-nums flex items-center justify-end gap-0.5',
                  positive ? 'text-destructive' : 'text-success',
                )}
              >
                {positive ? (
                  <ArrowUpRight className="size-3" aria-hidden="true" />
                ) : (
                  <ArrowDownRight className="size-3" aria-hidden="true" />
                )}
                {positive ? '+' : ''}
                {d.contribution.toFixed(2)}
              </span>
            </li>
          )
        })}
      </ul>
      <div className="mt-4 flex items-center gap-4 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-destructive inline-block" /> Pushes risk up
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-success inline-block" /> Pushes risk down
        </span>
      </div>
    </GlassCard>
  )
}

export function AttentionMapPanel() {
  return (
    <GlassCard className="p-5">
      <div className="flex items-start justify-between gap-2 mb-1">
        <h2 className="text-sm font-medium">Temporal Attention Map</h2>
        <span className="text-[10px] font-mono text-muted-foreground shrink-0">TFT encoder · head 3</span>
      </div>
      <p className="text-xs text-muted-foreground mb-4 text-pretty">
        Attention weights across the 12-hour input window. Recent rainfall and instability channels dominate the
        model&apos;s focus ahead of convective events.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1">
          <thead>
            <tr>
              <th className="text-left text-[10px] font-medium text-muted-foreground pr-2" scope="col">
                Feature
              </th>
              {ATTENTION_STEPS.map((s) => (
                <th key={s} className="text-[10px] font-mono font-normal text-muted-foreground" scope="col">
                  {s}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ATTENTION_FEATURES.map((f, fi) => (
              <tr key={f}>
                <th className="text-left text-xs font-medium pr-2 whitespace-nowrap" scope="row">
                  {f}
                </th>
                {ATTENTION_STEPS.map((s, ti) => {
                  const w = attentionWeight(fi, ti)
                  return (
                    <td key={s}>
                      <div
                        className="h-7 min-w-9 rounded-md bg-primary"
                        style={{ opacity: 0.08 + w * 0.92 }}
                        title={`${f} @ ${s}: ${w.toFixed(2)}`}
                      />
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlassCard>
  )
}

export function ModelCardPanel() {
  const rows = [
    { k: 'Model', v: 'XGBoost (champion) · TFT (challenger)' },
    { k: 'Task', v: 'Rainfall regression + hazard classification' },
    { k: 'Training data', v: 'Monsoon 2018–2025, 312 engineered features' },
    { k: 'Explanation fidelity', v: '0.94 (KernelSHAP vs TreeSHAP agreement)' },
    { k: 'Known limitations', v: 'Sparse gauges above 3,500m; IMERG latency ~4h' },
    { k: 'Intended use', v: 'Decision support for trained analysts — not a sole trigger for evacuation' },
  ]
  return (
    <GlassCard className="p-5">
      <div className="flex items-center gap-2 mb-4">
        <Brain className="size-4 text-primary" aria-hidden="true" />
        <h2 className="text-sm font-medium">Model Card & Governance</h2>
      </div>
      <dl className="flex flex-col gap-3">
        {rows.map((r) => (
          <div key={r.k} className="flex flex-col sm:flex-row sm:items-baseline gap-0.5 sm:gap-4">
            <dt className="text-xs text-muted-foreground w-40 shrink-0 uppercase tracking-wider">{r.k}</dt>
            <dd className="text-xs text-pretty">{r.v}</dd>
          </div>
        ))}
      </dl>
    </GlassCard>
  )
}

'use client'

import { useMemo, useState } from 'react'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { DISASTER_EVENTS } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

export function EventTimeline() {
  const [type, setType] = useState('All')
  const types = useMemo(() => ['All', ...Array.from(new Set(DISASTER_EVENTS.map((e) => e.type)))], [])

  const filtered = useMemo(
    () => DISASTER_EVENTS.filter((e) => type === 'All' || e.type === type),
    [type],
  )

  return (
    <GlassCard className="p-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-5">
        <h2 className="text-sm font-medium">Event Timeline</h2>
        <div className="flex items-center gap-1 flex-wrap">
          {types.map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              aria-pressed={type === t}
              className={cn(
                'px-2.5 py-1 rounded-full border text-[11px] font-medium transition-colors',
                type === t
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <ol className="flex flex-col">
        {filtered.map((e, i) => (
          <li key={e.id} className="flex gap-4">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'size-2.5 rounded-full shrink-0 mt-1.5',
                  e.severity === 'severe' ? 'bg-destructive' : e.severity === 'high' ? 'bg-warning' : 'bg-primary',
                )}
                aria-hidden="true"
              />
              {i < filtered.length - 1 && <span className="w-px flex-1 bg-border my-1" />}
            </div>
            <div className="pb-6 min-w-0 flex-1">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <span className="text-xs font-medium">
                    {e.type} — {e.location}
                  </span>
                  <span className="text-[11px] text-muted-foreground block">
                    {e.district} district ·{' '}
                    {new Date(e.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                  </span>
                </div>
                <RiskBadge risk={e.severity} />
              </div>
              <p className="text-xs text-muted-foreground mt-1.5 text-pretty max-w-2xl">{e.summary}</p>
              <div className="flex items-center gap-4 mt-2 text-[11px] font-mono tabular-nums">
                <span className="text-destructive">{e.deaths} deaths</span>
                <span className="text-muted-foreground">{e.affected.toLocaleString()} affected</span>
                <span className="text-muted-foreground">{'\u20B9'}{e.lossCr} Cr losses</span>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </GlassCard>
  )
}

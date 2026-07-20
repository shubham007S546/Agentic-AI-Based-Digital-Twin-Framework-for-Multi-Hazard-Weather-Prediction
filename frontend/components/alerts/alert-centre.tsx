'use client'

import { useMemo, useState, useEffect } from 'react'
import { Siren, MessageSquare, Radio, Smartphone, CheckCheck } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { RiskBadge } from '@/components/shared/risk-badge'
import { getActiveAlerts } from '@/lib/api/alerts'
import type { RiskLevel, AlertItem } from '@/types'
import { cn } from '@/lib/utils'

const SEVERITIES: ('all' | RiskLevel)[] = ['all', 'severe', 'high', 'moderate', 'low']

const CHANNELS = [
  { name: 'SMS (CAP gateway)', icon: Smartphone, reach: '2.4M subscribers', status: 'operational' },
  { name: 'District EOC hotline', icon: Radio, reach: '12 district EOCs', status: 'operational' },
  { name: 'Mobile app push', icon: MessageSquare, reach: '184K devices', status: 'operational' },
  { name: 'Siren network', icon: Siren, reach: '86 villages (Beas basin)', status: 'partial' },
]

function timeAgo(iso: string) {
  const diffMs = new Date().getTime() - new Date(iso).getTime()
  const mins = Math.round(diffMs / 60000)
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs} h ago`
  return `${Math.round(hrs / 24)} d ago`
}

export function AlertCentre() {
  const [severity, setSeverity] = useState<(typeof SEVERITIES)[number]>('all')
  const [acknowledged, setAcknowledged] = useState<Record<string, boolean>>({})
  const [alerts, setAlerts] = useState<AlertItem[]>([])

  useEffect(() => {
    getActiveAlerts().then(setAlerts).catch(console.error)
  }, [])

  const filtered = useMemo(
    () => alerts.filter((a) => severity === 'all' || a.severity === severity),
    [alerts, severity],
  )

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div className="xl:col-span-2 flex flex-col gap-4">
        <GlassCard className="p-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
            <h2 className="text-sm font-medium">Active Alerts</h2>
            <div className="flex items-center gap-1 flex-wrap" role="tablist" aria-label="Filter by severity">
              {SEVERITIES.map((s) => (
                <button
                  key={s}
                  role="tab"
                  aria-selected={severity === s}
                  onClick={() => setSeverity(s)}
                  className={cn(
                    'px-2.5 py-1 rounded-full border text-[11px] font-medium capitalize transition-colors',
                    severity === s
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <ul className="flex flex-col gap-3">
            {filtered.map((a) => (
              <li
                key={a.id}
                className={cn(
                  'rounded-xl border p-4 transition-colors',
                  a.severity === 'severe'
                    ? 'border-destructive/40 bg-destructive/5'
                    : a.severity === 'high'
                      ? 'border-warning/40 bg-warning/5'
                      : 'border-border bg-secondary/30',
                )}
              >
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{a.title}</span>
                      <RiskBadge risk={a.severity} />
                    </div>
                    <span className="text-[11px] text-muted-foreground block mt-0.5">
                      {a.district} district · {a.type} · issued {timeAgo(a.issuedAt)}
                    </span>
                  </div>
                  <button
                    onClick={() => setAcknowledged((prev) => ({ ...prev, [a.id]: !prev[a.id] }))}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors shrink-0',
                      acknowledged[a.id]
                        ? 'bg-success/15 text-success border-success/30'
                        : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
                    )}
                  >
                    <CheckCheck className="size-3.5" aria-hidden="true" />
                    {acknowledged[a.id] ? 'Acknowledged' : 'Acknowledge'}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-2 text-pretty">{a.message}</p>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="text-center text-xs text-muted-foreground py-8">No alerts at this severity level.</li>
            )}
          </ul>
        </GlassCard>
      </div>

      <div className="flex flex-col gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Dispatch Channels</h2>
          <ul className="flex flex-col gap-3">
            {CHANNELS.map((c) => (
              <li key={c.name} className="flex items-center gap-3">
                <div className="size-9 rounded-lg bg-secondary flex items-center justify-center shrink-0">
                  <c.icon className="size-4 text-primary" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <span className="text-xs font-medium block">{c.name}</span>
                  <span className="text-[10px] text-muted-foreground">{c.reach}</span>
                </div>
                <span
                  className={cn(
                    'size-2 rounded-full shrink-0',
                    c.status === 'operational' ? 'bg-success' : 'bg-warning',
                  )}
                  aria-label={c.status}
                />
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-3">Escalation Protocol</h2>
          <ol className="flex flex-col gap-2.5 text-xs text-muted-foreground list-none">
            {[
              'Model probability crosses district threshold',
              'Analyst verifies against radar and gauge data',
              'CAP alert drafted and severity assigned',
              'District EOC and SDMA notified simultaneously',
              'Public channels triggered for severe alerts',
            ].map((step, i) => (
              <li key={step} className="flex gap-2.5">
                <span className="size-5 rounded-full bg-secondary text-foreground flex items-center justify-center text-[10px] font-mono shrink-0">
                  {i + 1}
                </span>
                <span className="text-pretty">{step}</span>
              </li>
            ))}
          </ol>
        </GlassCard>
      </div>
    </div>
  )
}

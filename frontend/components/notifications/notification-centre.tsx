'use client'

import { useMemo, useState } from 'react'
import { Siren, Server, Brain, FileText, Check, CheckCheck } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { NOTIFICATIONS, type NotificationItem } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

const CATEGORY_META: Record<
  NotificationItem['category'],
  { label: string; icon: typeof Siren; tone: string }
> = {
  alert: { label: 'Alerts', icon: Siren, tone: 'text-destructive' },
  system: { label: 'System', icon: Server, tone: 'text-primary' },
  model: { label: 'Models', icon: Brain, tone: 'text-warning' },
  report: { label: 'Reports', icon: FileText, tone: 'text-success' },
}

type Filter = 'all' | NotificationItem['category'] | 'unread'

export function NotificationCentre() {
  const [items, setItems] = useState(NOTIFICATIONS)
  const [filter, setFilter] = useState<Filter>('all')

  const unreadCount = items.filter((n) => !n.read).length

  const filtered = useMemo(
    () =>
      items.filter((n) =>
        filter === 'all' ? true : filter === 'unread' ? !n.read : n.category === filter,
      ),
    [items, filter],
  )

  const markRead = (id: string) =>
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)))

  const markAllRead = () => setItems((prev) => prev.map((n) => ({ ...n, read: true })))

  const filters: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'unread', label: `Unread (${unreadCount})` },
    { key: 'alert', label: 'Alerts' },
    { key: 'model', label: 'Models' },
    { key: 'system', label: 'System' },
    { key: 'report', label: 'Reports' },
  ]

  return (
    <GlassCard className="p-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
        <div className="flex items-center gap-1 flex-wrap" role="tablist" aria-label="Filter notifications">
          {filters.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={cn(
                'px-2.5 py-1 rounded-full border text-[11px] font-medium transition-colors',
                filter === f.key
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          onClick={markAllRead}
          disabled={unreadCount === 0}
          className="inline-flex items-center gap-1.5 text-[11px] font-medium text-primary hover:underline disabled:text-muted-foreground disabled:no-underline"
        >
          <CheckCheck className="size-3.5" aria-hidden="true" />
          Mark all as read
        </button>
      </div>

      <ul className="flex flex-col divide-y divide-border/50">
        {filtered.map((n) => {
          const meta = CATEGORY_META[n.category]
          return (
            <li key={n.id} className={cn('flex gap-3 py-3.5', !n.read && 'bg-primary/[0.03] -mx-2 px-2 rounded-lg')}>
              <div className="size-9 rounded-lg bg-secondary flex items-center justify-center shrink-0">
                <meta.icon className={cn('size-4', meta.tone)} aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <span className={cn('text-xs', n.read ? 'font-normal text-muted-foreground' : 'font-medium')}>
                    {n.title}
                    {!n.read && <span className="ml-2 inline-block size-1.5 rounded-full bg-primary align-middle" aria-label="Unread" />}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0 font-mono">{n.time}</span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-0.5 text-pretty">{n.body}</p>
              </div>
              {!n.read && (
                <button
                  onClick={() => markRead(n.id)}
                  aria-label={`Mark "${n.title}" as read`}
                  className="self-center shrink-0 size-7 rounded-md border border-border bg-secondary flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
                >
                  <Check className="size-3.5" aria-hidden="true" />
                </button>
              )}
            </li>
          )
        })}
        {filtered.length === 0 && (
          <li className="text-center text-xs text-muted-foreground py-10">Nothing here — you&apos;re all caught up.</li>
        )}
      </ul>
    </GlassCard>
  )
}

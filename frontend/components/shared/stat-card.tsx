import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { GlassCard } from './glass-card'

export function StatCard({
  label,
  value,
  unit,
  icon: Icon,
  sub,
  tone = 'default',
}: {
  label: string
  value: string | number
  unit?: string
  icon: LucideIcon
  sub?: string
  tone?: 'default' | 'warning' | 'danger' | 'success'
}) {
  const toneClass =
    tone === 'danger'
      ? 'text-destructive'
      : tone === 'warning'
        ? 'text-warning'
        : tone === 'success'
          ? 'text-success'
          : 'text-primary'
  return (
    <GlassCard className="p-4 flex flex-col gap-2 transition-colors hover:border-primary/30">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        <Icon className={cn('size-4', toneClass)} aria-hidden="true" />
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-semibold tabular-nums">{value}</span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </div>
      {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
    </GlassCard>
  )
}

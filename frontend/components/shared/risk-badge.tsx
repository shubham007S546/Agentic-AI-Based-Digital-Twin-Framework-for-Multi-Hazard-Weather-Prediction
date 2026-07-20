import { cn } from '@/lib/utils'
import type { RiskLevel } from '@/types'

const STYLES: Record<RiskLevel, string> = {
  low: 'bg-success/15 text-success border-success/30',
  moderate: 'bg-warning/15 text-warning border-warning/30',
  high: 'bg-warning/20 text-warning border-warning/40',
  severe: 'bg-destructive/15 text-destructive border-destructive/30',
}

export function RiskBadge({ risk, className }: { risk: RiskLevel; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize',
        STYLES[risk],
        className,
      )}
    >
      {risk}
    </span>
  )
}

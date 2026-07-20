import { cn } from '@/lib/utils'
import type { ReactNode } from 'react'

export function GlassCard({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('glass rounded-xl shadow-lg shadow-black/20', className)}>{children}</div>
  )
}

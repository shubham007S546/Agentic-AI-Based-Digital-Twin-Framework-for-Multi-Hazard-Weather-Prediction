'use client'

import Link from 'next/link'
import dynamic from 'next/dynamic'
import { ArrowUpRight } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'

const BaseMap = dynamic(() => import('./base-map').then((m) => m.BaseMap), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-secondary/40 animate-pulse" />,
})

export function MiniMapCard() {
  return (
    <GlassCard className="relative overflow-hidden min-h-[320px]">
      <BaseMap interactive={false} />
      <div className="absolute inset-x-0 top-0 p-4 flex items-center justify-between bg-gradient-to-b from-background/80 to-transparent">
        <h2 className="text-sm font-medium">Risk Map</h2>
        <Link
          href="/map"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Open workspace
          <ArrowUpRight className="size-3.5" aria-hidden="true" />
        </Link>
      </div>
    </GlassCard>
  )
}

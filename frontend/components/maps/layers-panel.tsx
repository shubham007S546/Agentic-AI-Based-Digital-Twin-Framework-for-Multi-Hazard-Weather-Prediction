'use client'

import { useMemo } from 'react'
import { Layers } from 'lucide-react'
import { useAppStore } from '@/store/use-app-store'
import { cn } from '@/lib/utils'

const BASEMAPS = [
  { id: 'dark', label: 'Dark' },
  { id: 'satellite', label: 'Satellite' },
  { id: 'terrain', label: 'Terrain' },
  { id: 'road', label: 'Road' },
] as const

export function LayersPanel({ className }: { className?: string }) {
  const layers = useAppStore((s) => s.mapLayers)
  const toggleLayer = useAppStore((s) => s.toggleMapLayer)
  const basemap = useAppStore((s) => s.basemap)
  const setBasemap = useAppStore((s) => s.setBasemap)

  const groups = useMemo(() => {
    const g = new Map<string, typeof layers>()
    layers.forEach((l) => {
      const arr = g.get(l.group) ?? []
      arr.push(l)
      g.set(l.group, arr)
    })
    return Array.from(g.entries())
  }, [layers])

  return (
    <div className={cn('glass-strong rounded-xl p-4 w-64 flex flex-col gap-4', className)}>
      <div className="flex items-center gap-2">
        <Layers className="size-4 text-primary" aria-hidden="true" />
        <h3 className="text-sm font-medium">Map Layers</h3>
      </div>

      <div>
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
          Basemap
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {BASEMAPS.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => setBasemap(b.id)}
              className={cn(
                'rounded-lg border px-2 py-1.5 text-xs transition-colors',
                basemap === b.id
                  ? 'border-primary/50 bg-primary/15 text-primary'
                  : 'border-border bg-secondary/50 text-muted-foreground hover:text-foreground',
              )}
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto max-h-[40vh] pr-1">
        {groups.map(([group, items]) => (
          <div key={group}>
            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1.5">
              {group}
            </p>
            <ul className="flex flex-col gap-1">
              {items.map((l) => (
                <li key={l.id}>
                  <label className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary/60 cursor-pointer">
                    <span className="text-xs">{l.label}</span>
                    <input
                      type="checkbox"
                      checked={l.active}
                      onChange={() => toggleLayer(l.id)}
                      className="accent-[oklch(0.78_0.13_205)] size-3.5"
                    />
                  </label>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

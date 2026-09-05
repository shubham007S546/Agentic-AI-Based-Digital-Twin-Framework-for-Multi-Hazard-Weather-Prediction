import type { Metadata } from 'next'
import { History, Users, Banknote, AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericBarChart } from '@/components/charts/extra-charts'
import { EventTimeline } from '@/components/history/event-timeline'
import { DISASTER_EVENTS } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Disaster History | VARUNA',
  description: 'Historical disaster archive for Himachal Pradesh — cloudbursts, floods and landslides.',
}

export default function HistoryPage() {
  const totalDeaths = DISASTER_EVENTS.reduce((s, e) => s + e.deaths, 0)
  const totalAffected = DISASTER_EVENTS.reduce((s, e) => s + e.affected, 0)
  const totalLoss = DISASTER_EVENTS.reduce((s, e) => s + e.lossCr, 0)

  const byYear = Object.entries(
    DISASTER_EVENTS.reduce<Record<string, { events: number; lossCr: number }>>((acc, e) => {
      const y = e.date.slice(0, 4)
      acc[y] = acc[y] ?? { events: 0, lossCr: 0 }
      acc[y].events += 1
      acc[y].lossCr += e.lossCr
      return acc
    }, {}),
  )
    .map(([year, v]) => ({ year, ...v }))
    .sort((a, b) => a.year.localeCompare(b.year))

  const byType = Object.entries(
    DISASTER_EVENTS.reduce<Record<string, number>>((acc, e) => {
      acc[e.type] = (acc[e.type] ?? 0) + 1
      return acc
    }, {}),
  ).map(([type, count]) => ({ type, count }))

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Disaster History"
        description="Curated archive of major hydro-meteorological disasters across Himachal Pradesh, used for model training, validation and post-event analysis."
      />

      <section aria-label="Archive summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Major Events" value={DISASTER_EVENTS.length} icon={History} sub="2015 – 2025 curated set" />
        <StatCard label="Lives Lost" value={totalDeaths} icon={AlertTriangle} sub="Across recorded events" tone="danger" />
        <StatCard label="People Affected" value={`${(totalAffected / 1000).toFixed(0)}K`} icon={Users} sub="Displaced or impacted" tone="warning" />
        <StatCard label="Economic Loss" value={`\u20B9${(totalLoss / 1000).toFixed(1)}K`} unit="Cr" icon={Banknote} sub="Estimated direct damages" />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Events & Losses by Year</h2>
          <GenericBarChart
            data={byYear}
            xKey="year"
            series={[
              { key: 'events', name: 'Events' },
              { key: 'lossCr', name: 'Loss (Cr)' },
            ]}
          />
        </GlassCard>
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Events by Hazard Type</h2>
          <GenericBarChart data={byType} xKey="type" series={[{ key: 'count', name: 'Events' }]} />
        </GlassCard>
      </div>

      <EventTimeline />
    </div>
  )
}

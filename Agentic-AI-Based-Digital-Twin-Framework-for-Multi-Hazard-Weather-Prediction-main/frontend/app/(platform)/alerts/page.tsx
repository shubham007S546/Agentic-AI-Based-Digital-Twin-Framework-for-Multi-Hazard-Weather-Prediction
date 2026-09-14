import type { Metadata } from 'next'
import { Siren, Clock, Send, ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { AlertCentre } from '@/components/alerts/alert-centre'
import { getAllAlerts } from '@/lib/api/alerts'

export const metadata: Metadata = {
  title: 'Alert Centre | VARUNA',
  description: 'Operational alert management — active warnings, dispatch channels and escalation protocol.',
}

export default async function AlertsPage() {
  // Server-side fetch for initial stat card values — falls back to mock on error
  let alerts: Awaited<ReturnType<typeof getAllAlerts>>['data'] = []
  let totalAlerts = 0
  let severeCount = 0

  try {
    const result = await getAllAlerts(200)
    alerts       = result.data
    totalAlerts  = result.total
    severeCount  = alerts.filter((a) => a.severity === 'severe').length
  } catch {
    // Backend unreachable — client component will handle fallback
    totalAlerts = 0
    severeCount = 0
  }

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Alert Centre"
        description="Operational command view of all active warnings — verify model-triggered alerts, acknowledge receipt and track dispatch across every channel."
      />

      <section aria-label="Alert summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Active Alerts"
          value={totalAlerts || alerts.length}
          icon={Siren}
          sub={severeCount > 0 ? `${severeCount} severe` : 'All clear'}
          tone={severeCount > 0 ? 'danger' : 'default'}
        />
        <StatCard
          label="Avg Lead Time"
          value="4.6"
          unit="h"
          icon={Clock}
          sub="Model trigger to dispatch"
          tone="success"
        />
        <StatCard
          label="Dispatched Today"
          value={12}
          icon={Send}
          sub="Across all channels"
        />
        <StatCard
          label="False Alarm Rate"
          value="8.2"
          unit="%"
          icon={ShieldAlert}
          sub="Rolling 90 days"
        />
      </section>

      {/* Client component handles live refresh + acknowledge interactions */}
      <AlertCentre />
    </div>
  )
}

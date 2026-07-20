import type { Metadata } from 'next'
import { BellRing, Siren, Brain, Server } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { NotificationCentre } from '@/components/notifications/notification-centre'
import { NOTIFICATIONS } from '@/lib/mock/extended-data'

export const metadata: Metadata = {
  title: 'Notification Centre | VARUNA',
  description: 'Platform notifications across alerts, model training, system events and reports.',
}

export default function NotificationsPage() {
  const unread = NOTIFICATIONS.filter((n) => !n.read).length
  const alerts = NOTIFICATIONS.filter((n) => n.category === 'alert').length
  const model = NOTIFICATIONS.filter((n) => n.category === 'model').length

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Notification Centre"
        description="A single feed for everything that happens on the platform — hazard alerts, model training events, ingestion status and generated reports."
      />

      <section aria-label="Notification summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Unread" value={unread} icon={BellRing} sub="Awaiting review" tone={unread > 0 ? 'warning' : 'default'} />
        <StatCard label="Alert Events" value={alerts} icon={Siren} sub="Hazard-related" tone="danger" />
        <StatCard label="Model Events" value={model} icon={Brain} sub="Training and retraining" />
        <StatCard label="System Events" value={NOTIFICATIONS.length - alerts - model} icon={Server} sub="Ingestion and reports" />
      </section>

      <NotificationCentre />
    </div>
  )
}

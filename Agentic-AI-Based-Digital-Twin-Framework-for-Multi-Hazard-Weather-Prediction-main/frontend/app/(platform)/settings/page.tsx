import type { Metadata } from 'next'
import { PageHeader } from '@/components/shared/page-header'
import { SettingsPanel } from '@/components/settings/settings-panel'

export const metadata: Metadata = {
  title: 'Settings | VARUNA',
  description: 'Configure notifications, alert thresholds, interface preferences and API access.',
}

export default function SettingsPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Configure notifications, alert thresholds, interface preferences and API access for your account."
      />
      <SettingsPanel />
    </div>
  )
}

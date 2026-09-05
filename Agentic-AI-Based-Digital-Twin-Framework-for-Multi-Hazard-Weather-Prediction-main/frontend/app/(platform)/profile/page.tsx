import type { Metadata } from 'next'
import { PageHeader } from '@/components/shared/page-header'
import { ProfileView } from '@/components/profile/profile-view'

export const metadata: Metadata = {
  title: 'Profile | VARUNA',
  description: 'Your account details, district subscriptions, security status and recent activity.',
}

export default function ProfilePage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Profile"
        description="Manage your account details, district alert subscriptions and review your recent activity."
      />
      <ProfileView />
    </div>
  )
}

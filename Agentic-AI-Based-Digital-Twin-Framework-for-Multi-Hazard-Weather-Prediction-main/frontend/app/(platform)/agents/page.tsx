import type { Metadata } from 'next'
import { PageHeader } from '@/components/shared/page-header'
import { AgentControlRoom } from '@/components/agents/agent-control-room'

export const metadata: Metadata = {
  title: 'Agent Room | VARUNA',
  description: 'Live, inspectable multi-agent orchestration trace for VARUNA disaster intelligence.',
}

export default function AgentsPage() {
  return (
    <div className="p-4 lg:p-6">
      <PageHeader
        title="Agent Room"
        description="See how VARUNA agents collaborate in real time — from mission planning and tool calls to handoffs, evidence and decisions."
      />
      <div className="mt-6">
        <AgentControlRoom />
      </div>
    </div>
  )
}

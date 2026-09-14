import type { Metadata } from 'next'
import { PageHeader } from '@/components/shared/page-header'
import { AssistantChat } from '@/components/assistant/assistant-chat'

export const metadata: Metadata = {
  title: 'AI Assistant | VARUNA',
  description: 'Agentic AI assistant reasoning over live hazard, weather and model data.',
}

export default function AssistantPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6 min-h-[calc(100svh-3.5rem)]">
      <PageHeader
        title="AI Assistant"
        description="Agentic reasoning over live platform state — hazard predictions, gauges, terrain and model diagnostics with explainable answers."
      />
      <AssistantChat />
    </div>
  )
}

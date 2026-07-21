import type { Metadata } from 'next'
import { DigitalTwinWorkspace } from '@/components/digital-twin/twin-workspace'

export const metadata: Metadata = {
  title: 'Digital Twin | VARUNA',
  description:
    'Living virtual replica of terrain, rivers and infrastructure with historical replay and future simulation.',
}

export default function DigitalTwinPage() {
  return <DigitalTwinWorkspace />
}

import type { Metadata } from 'next'
import { DigitalTwinWorkspace } from '@/components/digital-twin/twin-workspace'
import { getHazardStations } from '@/lib/api/stations'
import { getRiverGauges } from '@/lib/api/hydrology'

export const metadata: Metadata = {
  title: 'Digital Twin | VARUNA',
  description:
    'Living virtual replica of terrain, rivers and infrastructure with historical replay and future simulation.',
}

export default async function DigitalTwinPage() {
  const [stations, gauges] = await Promise.all([
    getHazardStations(),
    getRiverGauges(),
  ])
  return <DigitalTwinWorkspace initialStations={stations} initialGauges={gauges} />
}

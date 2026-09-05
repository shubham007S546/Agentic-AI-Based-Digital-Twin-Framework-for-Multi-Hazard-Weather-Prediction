import type { Metadata } from 'next'
import { MapWorkspace } from '@/components/maps/map-workspace'

export const metadata: Metadata = {
  title: 'GIS Map | VARUNA',
  description: 'Interactive geospatial workspace with hazard, hydrology and infrastructure layers.',
}

export default function MapPage() {
  return <MapWorkspace />
}

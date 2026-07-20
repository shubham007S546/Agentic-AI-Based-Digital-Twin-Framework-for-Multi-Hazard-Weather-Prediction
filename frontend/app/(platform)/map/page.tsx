import type { Metadata } from 'next'
import { MapWorkspace } from '@/components/maps/map-workspace'
import { getCurrentWeather } from '@/lib/api/weather'
import { getHazardStations } from '@/lib/api/stations'
import { getActiveAlerts } from '@/lib/api/alerts'

export const metadata: Metadata = {
  title: 'GIS Map | VARUNA',
  description: 'Interactive geospatial workspace with hazard, hydrology and infrastructure layers.',
}

export default async function MapPage() {
  const [weather, stations, alerts] = await Promise.all([
    getCurrentWeather(),
    getHazardStations(),
    getActiveAlerts(50),
  ])

  return (
    <MapWorkspace
      initialWeather={weather}
      initialStations={stations}
      initialAlerts={alerts}
    />
  )
}

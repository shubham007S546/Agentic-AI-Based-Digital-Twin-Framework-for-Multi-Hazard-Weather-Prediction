'use client'

import { useEffect, useRef, useState } from 'react'
import maplibregl, { Map as MLMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { HAZARD_STATIONS, RISK_COLORS } from '@/lib/mock/data'
import { useAppStore } from '@/store/use-app-store'
import { apiFetch } from '@/lib/api/client'

const BASEMAP_TILES: Record<string, { tiles: string[]; attribution: string }> = {
  dark: {
    tiles: [
      'https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: 'Esri, HERE, Garmin, © OpenStreetMap contributors, and the GIS user community',
  },
  satellite: {
    tiles: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
  terrain: {
    tiles: ['https://tile.opentopomap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors, SRTM | © OpenTopoMap',
  },
  road: {
    tiles: [
      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    ],
    attribution: '© OpenStreetMap contributors',
  },
}

function buildStyle(basemap: string): maplibregl.StyleSpecification {
  const src = BASEMAP_TILES[basemap] ?? BASEMAP_TILES.dark
  return {
    version: 8,
    sources: {
      base: {
        type: 'raster',
        tiles: src.tiles,
        tileSize: 256,
        attribution: src.attribution,
      },
    },
    layers: [{ id: 'base', type: 'raster', source: 'base' }],
  }
}

export function BaseMap({
  interactive = true,
  showStations = true,
  className,
  onStationClick,
}: {
  interactive?: boolean
  showStations?: boolean
  className?: string
  onStationClick?: (id: string) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const markersRef = useRef<maplibregl.Marker[]>([])
  const basemap = useAppStore((s) => s.basemap)
  const layers = useAppStore((s) => s.mapLayers)
  const [liveStations, setLiveStations] = useState<typeof HAZARD_STATIONS>(HAZARD_STATIONS)

  const riskActive = layers.find((l) => l.id === 'risk')?.active ?? true

  // Fetch live stations from backend if available
  useEffect(() => {
    let unmounted = false
    apiFetch<{ data: any[] }>('/weather/stations')
      .then((res) => {
        if (unmounted || !res?.data?.length) return
        const mapped = res.data.map((st) => ({
          id: st.id || `st-${st.name.toLowerCase()}`,
          name: st.name,
          district: st.district,
          lat: st.lat,
          lng: st.lng,
          risk: st.risk || 'low',
          probability: st.probability || 20,
          metric: st.metric || 0,
        }))
        // Merge with existing fallback stations to maintain complete coverage
        const existingNames = new Set(mapped.map((m) => m.name.toLowerCase()))
        const combined = [...mapped, ...HAZARD_STATIONS.filter((st) => !existingNames.has(st.name.toLowerCase()))]
        setLiveStations(combined as any)
      })
      .catch(() => {})
    return () => {
      unmounted = true
    }
  }, [])

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(basemap || 'dark'),
      center: [77.1, 31.7],
      zoom: 7.4,
      interactive,
      attributionControl: { compact: true },
    })

    if (interactive) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    }

    map.on('load', () => {
      map.resize()
    })

    // ResizeObserver to trigger map.resize() when container size settles
    const observer = new ResizeObserver(() => {
      map.resize()
    })
    observer.observe(containerRef.current)

    mapRef.current = map

    return () => {
      observer.disconnect()
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []
      map.remove()
      mapRef.current = null
    }
  }, [interactive])

  // Basemap switching
  useEffect(() => {
    if (mapRef.current) {
      mapRef.current.setStyle(buildStyle(basemap))
    }
  }, [basemap])

  // Station markers rendering
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []
    if (!showStations || !riskActive) return

    liveStations.forEach((st) => {
      const el = document.createElement('button')
      el.type = 'button'
      el.setAttribute('aria-label', `${st.name} station, ${st.risk} risk`)
      el.style.cssText =
        'position:relative;width:18px;height:18px;background:transparent;border:none;cursor:pointer;'
      const color = RISK_COLORS[st.risk] || RISK_COLORS.low
      el.innerHTML = `
        <span style="position:absolute;inset:0;border-radius:9999px;background:${color};opacity:.35;animation:pulse-ring 2.4s ease-out infinite;"></span>
        <span style="position:absolute;inset:4px;border-radius:9999px;background:${color};border:2px solid rgba(255,255,255,.7);"></span>
      `
      el.addEventListener('click', () => onStationClick?.(st.id))

      const popup = new maplibregl.Popup({ offset: 14, closeButton: false }).setHTML(
        `<div style="font-family:var(--font-geist-sans),sans-serif;background:#1a2030;color:#e8ecf4;padding:10px 12px;border-radius:10px;min-width:160px;border:1px solid rgba(255,255,255,.1)">
          <div style="font-weight:600;font-size:13px">${st.name}</div>
          <div style="font-size:11px;color:#93a0b4;margin-top:2px">${st.district} district</div>
          <div style="font-size:11px;margin-top:6px;display:flex;justify-content:space-between"><span>Risk</span><b style="color:${color};text-transform:capitalize">${st.risk}</b></div>
          <div style="font-size:11px;display:flex;justify-content:space-between"><span>Probability</span><b>${st.probability}%</b></div>
          <div style="font-size:11px;display:flex;justify-content:space-between"><span>24h rain</span><b>${st.metric} mm</b></div>
        </div>`,
      )

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([st.lng, st.lat])
        .setPopup(popup)
        .addTo(map)
      markersRef.current.push(marker)
    })
  }, [showStations, riskActive, basemap, liveStations, onStationClick])

  return (
    <div
      ref={containerRef}
      className={className ?? 'absolute inset-0 w-full h-full min-h-full'}
      style={{ width: '100%', height: '100%' }}
    />
  )
}

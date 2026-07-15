'use client'

import { useEffect, useRef } from 'react'
import maplibregl, { Map as MLMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { HAZARD_STATIONS, RISK_COLORS } from '@/lib/mock/data'
import { useAppStore } from '@/store/use-app-store'

const BASEMAP_TILES: Record<string, { tiles: string[]; attribution: string }> = {
  dark: {
    tiles: [
      'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
      'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
    ],
    attribution: '© OpenStreetMap contributors © CARTO',
  },
  satellite: {
    tiles: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
  terrain: {
    tiles: ['https://a.tile.opentopomap.org/{z}/{x}/{y}.png'],
    attribution: '© OpenStreetMap contributors, SRTM | © OpenTopoMap',
  },
  road: {
    tiles: [
      'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
      'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
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

  const riskActive = layers.find((l) => l.id === 'risk')?.active ?? true

  // init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle('dark'),
      center: [77.1, 31.7],
      zoom: 7.4,
      interactive,
      attributionControl: { compact: true },
    })
    if (interactive) {
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
      map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    }
    mapRef.current = map
    return () => {
      markersRef.current.forEach((m) => m.remove())
      markersRef.current = []
      map.remove()
      mapRef.current = null
    }
  }, [interactive])

  // basemap switching
  useEffect(() => {
    mapRef.current?.setStyle(buildStyle(basemap))
  }, [basemap])

  // station markers
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []
    if (!showStations || !riskActive) return

    HAZARD_STATIONS.forEach((st) => {
      const el = document.createElement('button')
      el.type = 'button'
      el.setAttribute('aria-label', `${st.name} station, ${st.risk} risk`)
      el.style.cssText =
        'position:relative;width:18px;height:18px;background:transparent;border:none;cursor:pointer;'
      const color = RISK_COLORS[st.risk]
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
  }, [showStations, riskActive, basemap, onStationClick])

  return <div ref={containerRef} className={className ?? 'absolute inset-0'} />
}

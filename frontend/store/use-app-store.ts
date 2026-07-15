'use client'

import { create } from 'zustand'
import type { MapLayerDef } from '@/types'

export const DEFAULT_MAP_LAYERS: MapLayerDef[] = [
  { id: 'rainfall', label: 'Rainfall Intensity', group: 'Weather', active: true },
  { id: 'clouds', label: 'Cloud Cover', group: 'Weather', active: false },
  { id: 'risk', label: 'Risk Zones', group: 'Prediction', active: true },
  { id: 'prediction', label: 'AI Prediction Layer', group: 'Prediction', active: false },
  { id: 'historical', label: 'Historical Events', group: 'Prediction', active: false },
  { id: 'rivers', label: 'Rivers & Discharge', group: 'Hydrology', active: true },
  { id: 'ndvi', label: 'NDVI', group: 'Environment', active: false },
  { id: 'dem', label: 'DEM / Elevation', group: 'Terrain', active: false },
  { id: 'slope', label: 'Slope', group: 'Terrain', active: false },
  { id: 'hospitals', label: 'Hospitals', group: 'Infrastructure', active: false },
  { id: 'schools', label: 'Schools', group: 'Infrastructure', active: false },
  { id: 'bridges', label: 'Roads & Bridges', group: 'Infrastructure', active: false },
  { id: 'population', label: 'Population Density', group: 'Demographics', active: false },
]

interface AppState {
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  setSidebarCollapsed: (v: boolean) => void
  mapLayers: MapLayerDef[]
  toggleMapLayer: (id: string) => void
  basemap: 'dark' | 'satellite' | 'terrain' | 'road'
  setBasemap: (b: AppState['basemap']) => void
  mapFullscreen: boolean
  setMapFullscreen: (v: boolean) => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  mapLayers: DEFAULT_MAP_LAYERS,
  toggleMapLayer: (id) =>
    set((s) => ({
      mapLayers: s.mapLayers.map((l) => (l.id === id ? { ...l, active: !l.active } : l)),
    })),
  basemap: 'dark',
  setBasemap: (b) => set({ basemap: b }),
  mapFullscreen: false,
  setMapFullscreen: (v) => set({ mapFullscreen: v }),
}))

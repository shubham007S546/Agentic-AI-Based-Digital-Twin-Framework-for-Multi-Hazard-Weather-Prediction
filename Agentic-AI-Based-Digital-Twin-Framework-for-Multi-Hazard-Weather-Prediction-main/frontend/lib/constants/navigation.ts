import {
  LayoutDashboard,
  Map,
  Globe,
  CloudSun,
  CalendarClock,
  CloudRain,
  CloudLightning,
  Waves,
  Mountain,
  Droplets,
  Satellite,
  Radio,
  Bot,
  BarChart3,
  Brain,
  FileText,
  History,
  Siren,
} from 'lucide-react'
import type { NavSection } from '@/types'

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Command',
    items: [
      { label: 'Situational Dashboard', href: '/dashboard', icon: LayoutDashboard },
      { label: 'GIS Risk Map', href: '/map', icon: Map },
      { label: 'Digital Twin', href: '/digital-twin', icon: Globe },
    ],
  },
  {
    title: 'Atmospheric',
    items: [
      { label: 'Live Weather', href: '/weather', icon: CloudSun },
      { label: 'Multi-Day Forecast', href: '/forecast', icon: CalendarClock },
    ],
  },
  {
    title: 'Hazard Intelligence',
    items: [
      { label: 'Rainfall Prediction', href: '/rainfall', icon: CloudRain },
      { label: 'Cloudburst', href: '/cloudburst', icon: CloudLightning },
      { label: 'Flash Flood', href: '/flood', icon: Waves },
      { label: 'Landslide', href: '/landslide', icon: Mountain },
    ],
  },
  {
    title: 'Earth Observation',
    items: [
      { label: 'Hydrology', href: '/hydrology', icon: Droplets },
      { label: 'Satellite Imagery', href: '/satellite', icon: Satellite },
    ],
  },
  {
    title: 'AI & Models',
    items: [
      { label: 'Agent Orchestration', href: '/agents', icon: Radio },
      { label: 'AI Assistant', href: '/assistant', icon: Bot },
      { label: 'Model Performance', href: '/analytics', icon: BarChart3 },
      { label: 'Explainable AI', href: '/explainable-ai', icon: Brain },
    ],
  },
  {
    title: 'Operations',
    items: [
      { label: 'Alert Centre', href: '/alerts', icon: Siren },
      { label: 'Disaster History', href: '/history', icon: History },
      { label: 'Reports', href: '/reports', icon: FileText },
    ],
  },
]

export const PLATFORM_NAME = 'VARUNA'
export const PLATFORM_TAGLINE = 'Multi-Hazard Intelligence'

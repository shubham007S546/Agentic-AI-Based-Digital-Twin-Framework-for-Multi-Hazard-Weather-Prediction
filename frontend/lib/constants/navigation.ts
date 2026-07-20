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
  Layers,
  Leaf,
  Building2,
  Users,
  Satellite,
  Thermometer,
  Bot,
  BarChart3,
  Brain,
  FlaskConical,
  FileText,
  Settings,
  Database,
  History,
  Siren,
  BellRing,
  UserCircle,
  ShieldCheck,
} from 'lucide-react'
import type { NavSection } from '@/types'

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
      { label: 'GIS Map', href: '/map', icon: Map },
      { label: 'Digital Twin', href: '/digital-twin', icon: Globe },
    ],
  },
  {
    title: 'Weather',
    items: [
      { label: 'Live Weather', href: '/weather', icon: CloudSun },
      { label: 'Forecast', href: '/forecast', icon: CalendarClock },
    ],
  },
  {
    title: 'Hazard Prediction',
    items: [
      { label: 'Rainfall', href: '/rainfall', icon: CloudRain },
      { label: 'Cloudburst', href: '/cloudburst', icon: CloudLightning },
      { label: 'Flood', href: '/flood', icon: Waves },
      { label: 'Landslide', href: '/landslide', icon: Mountain },
    ],
  },
  {
    title: 'Earth Systems',
    items: [
      { label: 'Hydrology', href: '/hydrology', icon: Droplets },
      { label: 'Terrain', href: '/terrain', icon: Layers },
      { label: 'Vegetation', href: '/vegetation', icon: Leaf },
      { label: 'Infrastructure', href: '/infrastructure', icon: Building2 },
      { label: 'Population', href: '/population', icon: Users },
      { label: 'Satellite', href: '/satellite', icon: Satellite },
      { label: 'Climate', href: '/climate', icon: Thermometer },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { label: 'AI Assistant', href: '/assistant', icon: Bot },
      { label: 'Model Analytics', href: '/analytics', icon: BarChart3 },
      { label: 'Explainable AI', href: '/explainable-ai', icon: Brain },
      { label: 'Research Dashboard', href: '/research', icon: FlaskConical },
    ],
  },
  {
    title: 'Data',
    items: [
      { label: 'Dataset Explorer', href: '/datasets', icon: Database },
      { label: 'Disaster History', href: '/history', icon: History },
    ],
  },
  {
    title: 'Platform',
    items: [
      { label: 'Alert Centre', href: '/alerts', icon: Siren },
      { label: 'Notifications', href: '/notifications', icon: BellRing },
      { label: 'Reports', href: '/reports', icon: FileText },
      { label: 'Administration', href: '/admin', icon: ShieldCheck },
      { label: 'Profile', href: '/profile', icon: UserCircle },
      { label: 'Settings', href: '/settings', icon: Settings },
    ],
  },
]

export const PLATFORM_NAME = 'VARUNA'
export const PLATFORM_TAGLINE = 'Disaster Intelligence Platform'

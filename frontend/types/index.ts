import type { LucideIcon } from 'lucide-react'

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe'

export interface NavItem {
  label: string
  href: string
  icon: LucideIcon
}

export interface NavSection {
  title: string
  items: NavItem[]
}

export interface WeatherSnapshot {
  temperature: number
  humidity: number
  pressure: number
  windSpeed: number
  windDirection: string
  rainfall: number
  dewPoint: number
  visibility: number
  uvIndex: number
  cloudCover: number
  condition: string
  updatedAt: string
}

export interface ForecastDay {
  date: string
  day: string
  tempMin: number
  tempMax: number
  rainfall: number
  rainProbability: number
  humidity: number
  windSpeed: number
  condition: string
}

export interface HazardStation {
  id: string
  name: string
  district: string
  lat: number
  lng: number
  risk: RiskLevel
  probability: number
  metric: number
}

export interface RiverGauge {
  id: string
  river: string
  station: string
  level: number
  dangerLevel: number
  discharge: number
  trend: 'rising' | 'falling' | 'steady'
}

export interface ModelMetrics {
  name: string
  category: 'ml' | 'dl' | 'transformer'
  mae: number
  rmse: number
  r2: number
  mape: number
  precision: number
  recall: number
  f1: number
  mcc: number
  trainingTime: number
  inferenceMs: number
  params: string
  status: 'trained' | 'training' | 'planned'
}

export interface DatasetInfo {
  name: string
  source: string
  category: string
  records: string
  sizeMB: number
  resolution: string
  status: 'collected' | 'validating' | 'processing'
  updatedAt: string
}

export interface FeatureImportance {
  feature: string
  importance: number
  shap: number
}

export interface PipelineStage {
  name: string
  status: 'complete' | 'active' | 'upcoming'
  description: string
}

export interface AlertItem {
  id: string
  title: string
  district: string
  severity: RiskLevel
  type: string
  issuedAt: string
  message: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export interface MapLayerDef {
  id: string
  label: string
  group: string
  active: boolean
}

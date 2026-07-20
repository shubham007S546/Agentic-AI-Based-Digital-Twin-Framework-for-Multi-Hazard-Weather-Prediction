import type { RiskLevel } from '@/types'

/* ------------------------------- Hydrology ------------------------------- */

export const DISCHARGE_SERIES = Array.from({ length: 30 }, (_, i) => ({
  day: `Jun ${i + 16 > 30 ? `Jul ${i - 14}` : i + 16}`.replace('Jun Jul', 'Jul'),
  beas: Number((820 + Math.sin(i / 3.2) * 180 + i * 16 + Math.random() * 40).toFixed(0)),
  sutlej: Number((640 + Math.sin(i / 4.1) * 120 + i * 9 + Math.random() * 30).toFixed(0)),
  ravi: Number((310 + Math.sin(i / 3.8) * 60 + i * 3 + Math.random() * 20).toFixed(0)),
}))

export const CATCHMENTS = [
  { basin: 'Beas', area: 12560, gauges: 14, snowCover: 34, soilMoisture: 86, runoffIndex: 0.72, risk: 'severe' as RiskLevel },
  { basin: 'Sutlej', area: 20398, gauges: 18, snowCover: 41, soilMoisture: 71, runoffIndex: 0.58, risk: 'high' as RiskLevel },
  { basin: 'Ravi', area: 5451, gauges: 8, snowCover: 22, soilMoisture: 64, runoffIndex: 0.44, risk: 'moderate' as RiskLevel },
  { basin: 'Chenab', area: 7500, gauges: 6, snowCover: 48, soilMoisture: 52, runoffIndex: 0.38, risk: 'moderate' as RiskLevel },
  { basin: 'Yamuna (Pabbar)', area: 2320, gauges: 4, snowCover: 12, soilMoisture: 58, runoffIndex: 0.31, risk: 'low' as RiskLevel },
]

export const GROUNDWATER_LEVELS = [
  { month: 'Jan', level: 12.4 }, { month: 'Feb', level: 12.8 }, { month: 'Mar', level: 13.2 },
  { month: 'Apr', level: 13.9 }, { month: 'May', level: 14.6 }, { month: 'Jun', level: 13.1 },
  { month: 'Jul', level: 10.8 }, { month: 'Aug', level: 9.6 }, { month: 'Sep', level: 10.2 },
  { month: 'Oct', level: 11.0 }, { month: 'Nov', level: 11.6 }, { month: 'Dec', level: 12.1 },
]

/* -------------------------------- Terrain -------------------------------- */

export const ELEVATION_PROFILE = Array.from({ length: 40 }, (_, i) => ({
  km: i * 4,
  elevation: Number((600 + Math.sin(i / 5) * 900 + i * 68 + Math.cos(i / 2.2) * 240).toFixed(0)),
}))

export const ELEVATION_BANDS = [
  { band: '< 500m', areaPct: 8, landslides: 2 },
  { band: '500–1000m', areaPct: 16, landslides: 11 },
  { band: '1000–2000m', areaPct: 27, landslides: 38 },
  { band: '2000–3000m', areaPct: 24, landslides: 31 },
  { band: '3000–4000m', areaPct: 15, landslides: 14 },
  { band: '> 4000m', areaPct: 10, landslides: 4 },
]

export const SLOPE_DISTRIBUTION = [
  { range: '0–10°', areaPct: 14, stability: 'Stable' },
  { range: '10–20°', areaPct: 22, stability: 'Stable' },
  { range: '20–30°', areaPct: 28, stability: 'Marginal' },
  { range: '30–40°', areaPct: 21, stability: 'Unstable' },
  { range: '40–50°', areaPct: 11, stability: 'Critical' },
  { range: '> 50°', areaPct: 4, stability: 'Critical' },
]

export const ASPECT_DISTRIBUTION = [
  { aspect: 'N', areaPct: 11, wetness: 0.72 },
  { aspect: 'NE', areaPct: 13, wetness: 0.68 },
  { aspect: 'E', areaPct: 12, wetness: 0.58 },
  { aspect: 'SE', areaPct: 14, wetness: 0.49 },
  { aspect: 'S', areaPct: 15, wetness: 0.41 },
  { aspect: 'SW', areaPct: 13, wetness: 0.46 },
  { aspect: 'W', areaPct: 11, wetness: 0.55 },
  { aspect: 'NW', areaPct: 11, wetness: 0.66 },
]

/* ------------------------------- Vegetation ------------------------------ */

export const NDVI_SERIES = Array.from({ length: 24 }, (_, i) => ({
  period: `P${i + 1}`,
  ndvi: Number((0.42 + Math.sin((i - 4) / 3.6) * 0.18 + Math.random() * 0.02).toFixed(3)),
  evi: Number((0.31 + Math.sin((i - 4) / 3.6) * 0.13 + Math.random() * 0.02).toFixed(3)),
}))

export const LST_SERIES = Array.from({ length: 24 }, (_, i) => ({
  period: `P${i + 1}`,
  day: Number((18 + Math.sin((i - 5) / 3.4) * 10 + Math.random()).toFixed(1)),
  night: Number((6 + Math.sin((i - 5) / 3.4) * 7 + Math.random()).toFixed(1)),
}))

export const LAND_COVER = [
  { class: 'Dense Forest', pct: 27.4 },
  { class: 'Open Forest', pct: 14.2 },
  { class: 'Scrubland', pct: 12.8 },
  { class: 'Cropland', pct: 16.6 },
  { class: 'Grassland', pct: 9.4 },
  { class: 'Snow / Glacier', pct: 8.9 },
  { class: 'Barren / Rock', pct: 7.6 },
  { class: 'Built-up', pct: 2.1 },
  { class: 'Water', pct: 1.0 },
]

/* ------------------------------- Satellite ------------------------------- */

export const SATELLITE_PASSES = [
  { satellite: 'GPM Core', sensor: 'DPR / GMI', nextPass: '11:42 IST', revisit: '~3h', product: 'IMERG precipitation', status: 'nominal' },
  { satellite: 'Terra', sensor: 'MODIS', nextPass: '10:28 IST', revisit: 'Daily', product: 'LST, cloud, NDVI', status: 'nominal' },
  { satellite: 'Aqua', sensor: 'MODIS', nextPass: '13:36 IST', revisit: 'Daily', product: 'LST, water vapor', status: 'nominal' },
  { satellite: 'Sentinel-1A', sensor: 'C-SAR', nextPass: '18:04 IST', revisit: '6 days', product: 'Soil moisture, flood extent', status: 'nominal' },
  { satellite: 'Sentinel-2B', sensor: 'MSI', nextPass: 'Jul 17', revisit: '5 days', product: 'NDVI 10m, land cover', status: 'nominal' },
  { satellite: 'INSAT-3DR', sensor: 'Imager / Sounder', nextPass: 'Geostationary', revisit: '15min', product: 'Cloud motion, TPW', status: 'nominal' },
  { satellite: 'Landsat 9', sensor: 'OLI-2 / TIRS-2', nextPass: 'Jul 19', revisit: '16 days', product: 'Thermal, land change', status: 'degraded' },
]

export const CLOUD_TOP_TEMP = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  ctt: Number((-32 - Math.max(0, Math.sin((i - 8) / 3.4)) * 34 - Math.random() * 4).toFixed(1)),
  threshold: -65,
}))

/* -------------------------------- Climate -------------------------------- */

export const TEMP_ANOMALY = Array.from({ length: 34 }, (_, i) => ({
  year: 1992 + i,
  anomaly: Number((-0.3 + i * 0.045 + Math.sin(i / 2.4) * 0.22).toFixed(2)),
}))

export const PRECIP_ANOMALY = Array.from({ length: 34 }, (_, i) => ({
  year: 1992 + i,
  anomaly: Number((Math.sin(i / 2.1) * 12 + (i > 20 ? (i - 20) * 1.4 : 0) + (Math.random() - 0.5) * 6).toFixed(1)),
}))

export const EXTREME_EVENT_TREND = [
  { decade: '1990s', cloudbursts: 8, floods: 14, landslides: 42 },
  { decade: '2000s', cloudbursts: 14, floods: 19, landslides: 61 },
  { decade: '2010s', cloudbursts: 27, floods: 26, landslides: 94 },
  { decade: '2020s', cloudbursts: 38, floods: 31, landslides: 128 },
]

export const CLIMATE_INDICES = [
  { index: 'ENSO (ONI)', value: '+0.8', phase: 'El Niño (weak)', influence: 'Suppressed monsoon breaks' },
  { index: 'IOD (DMI)', value: '+0.4', phase: 'Positive (weak)', influence: 'Enhanced moisture flux' },
  { index: 'MJO Phase', value: '5', phase: 'Active over Bay of Bengal', influence: 'Convection enhancement 5–9 days' },
  { index: 'Monsoon Index', value: '112%', phase: 'Above normal', influence: 'LPA exceedance, active spell' },
]

/* ------------------------------- Population ------------------------------ */

export const DISTRICT_POPULATION = [
  { district: 'Kangra', population: 1510075, density: 263, exposed: 182000, vulnerability: 0.62, risk: 'high' as RiskLevel },
  { district: 'Mandi', population: 999777, density: 253, exposed: 164000, vulnerability: 0.68, risk: 'high' as RiskLevel },
  { district: 'Shimla', population: 814010, density: 159, exposed: 96000, vulnerability: 0.52, risk: 'moderate' as RiskLevel },
  { district: 'Solan', population: 580320, density: 300, exposed: 61000, vulnerability: 0.44, risk: 'moderate' as RiskLevel },
  { district: 'Kullu', population: 437903, density: 80, exposed: 118000, vulnerability: 0.74, risk: 'severe' as RiskLevel },
  { district: 'Chamba', population: 519080, density: 80, exposed: 74000, vulnerability: 0.66, risk: 'high' as RiskLevel },
  { district: 'Una', population: 521173, density: 338, exposed: 32000, vulnerability: 0.31, risk: 'low' as RiskLevel },
  { district: 'Hamirpur', population: 454768, density: 407, exposed: 28000, vulnerability: 0.29, risk: 'low' as RiskLevel },
  { district: 'Bilaspur', population: 381956, density: 327, exposed: 34000, vulnerability: 0.35, risk: 'moderate' as RiskLevel },
  { district: 'Sirmaur', population: 529855, density: 188, exposed: 47000, vulnerability: 0.48, risk: 'moderate' as RiskLevel },
  { district: 'Kinnaur', population: 84121, density: 13, exposed: 21000, vulnerability: 0.71, risk: 'high' as RiskLevel },
  { district: 'Lahaul & Spiti', population: 31564, density: 2, exposed: 9000, vulnerability: 0.64, risk: 'moderate' as RiskLevel },
]

export const AGE_PYRAMID = [
  { group: '0–14', male: 8.4, female: 7.9 },
  { group: '15–29', male: 13.2, female: 12.6 },
  { group: '30–44', male: 12.1, female: 11.8 },
  { group: '45–59', male: 9.6, female: 9.4 },
  { group: '60–74', male: 5.8, female: 6.1 },
  { group: '75+', male: 1.4, female: 1.7 },
]

/* ----------------------------- Infrastructure ---------------------------- */

export const INFRA_SUMMARY = [
  { type: 'Hospitals & PHCs', count: 642, atRisk: 38, critical: 9 },
  { type: 'Schools & Colleges', count: 17862, atRisk: 412, critical: 64 },
  { type: 'Bridges', count: 2141, atRisk: 186, critical: 27 },
  { type: 'Hydro Projects', count: 168, atRisk: 22, critical: 6 },
  { type: 'National Highways (km)', count: 2607, atRisk: 314, critical: 82 },
  { type: 'Power Substations', count: 486, atRisk: 41, critical: 8 },
]

export const CRITICAL_ASSETS = [
  { id: 'if-1', name: 'Zonal Hospital Mandi', type: 'Hospital', district: 'Mandi', hazard: 'Flood (Beas)', distanceM: 120, risk: 'severe' as RiskLevel },
  { id: 'if-2', name: 'Victoria Bridge', type: 'Bridge', district: 'Mandi', hazard: 'Flood (Beas)', distanceM: 0, risk: 'severe' as RiskLevel },
  { id: 'if-3', name: 'NH-3 Hanogi Stretch', type: 'Highway', district: 'Mandi', hazard: 'Landslide', distanceM: 0, risk: 'high' as RiskLevel },
  { id: 'if-4', name: 'Pandoh Dam', type: 'Hydro', district: 'Mandi', hazard: 'Inflow surge', distanceM: 0, risk: 'high' as RiskLevel },
  { id: 'if-5', name: 'Kullu District Hospital', type: 'Hospital', district: 'Kullu', hazard: 'Flood (Beas)', distanceM: 340, risk: 'high' as RiskLevel },
  { id: 'if-6', name: 'Aut Tunnel Portal', type: 'Highway', district: 'Mandi', hazard: 'Landslide', distanceM: 80, risk: 'moderate' as RiskLevel },
  { id: 'if-7', name: 'Larji Power House', type: 'Hydro', district: 'Kullu', hazard: 'Flood (Beas)', distanceM: 40, risk: 'high' as RiskLevel },
  { id: 'if-8', name: 'GSSS Bhuntar', type: 'School', district: 'Kullu', hazard: 'Flood (Parvati)', distanceM: 260, risk: 'moderate' as RiskLevel },
]

/* ----------------------------- Disaster History -------------------------- */

export interface DisasterEvent {
  id: string
  date: string
  type: string
  district: string
  location: string
  deaths: number
  affected: number
  lossCr: number
  severity: RiskLevel
  summary: string
}

export const DISASTER_EVENTS: DisasterEvent[] = [
  { id: 'ev-1', date: '2025-08-14', type: 'Cloudburst', district: 'Kullu', location: 'Malana Nala', deaths: 7, affected: 3400, lossCr: 210, severity: 'severe', summary: 'Cloudburst above Malana triggered flash flood damaging the power project intake and village access.' },
  { id: 'ev-2', date: '2025-07-09', type: 'Flood', district: 'Mandi', location: 'Beas at Pandoh', deaths: 3, affected: 12800, lossCr: 480, severity: 'severe', summary: 'Extreme inflow forced emergency releases; low-lying markets of Mandi town inundated.' },
  { id: 'ev-3', date: '2024-08-01', type: 'Cloudburst', district: 'Shimla', location: 'Rampur (Samej)', deaths: 21, affected: 5200, lossCr: 320, severity: 'severe', summary: 'Night-time cloudburst destroyed Samej village; hydro project workers among casualties.' },
  { id: 'ev-4', date: '2023-07-10', type: 'Flood', district: 'Kullu', location: 'Beas valley', deaths: 26, affected: 84000, lossCr: 2100, severity: 'severe', summary: 'Historic monsoon flood; NH-3 washed out at multiple points, Manali cut off for days.' },
  { id: 'ev-5', date: '2023-08-14', type: 'Landslide', district: 'Shimla', location: 'Summer Hill', deaths: 20, affected: 1800, lossCr: 96, severity: 'severe', summary: 'Deep-seated failure following 72h saturation destroyed the Shiv temple area.' },
  { id: 'ev-6', date: '2022-08-20', type: 'Flash Flood', district: 'Kangra', location: 'Chakki Khad', deaths: 2, affected: 4100, lossCr: 150, severity: 'high', summary: 'Railway bridge collapse over Chakki after extreme bedload transport.' },
  { id: 'ev-7', date: '2021-07-27', type: 'Cloudburst', district: 'Lahaul & Spiti', location: 'Tozing Nala', deaths: 10, affected: 900, lossCr: 44, severity: 'high', summary: 'Multiple cloudbursts across Lahaul valley; Chandrabhaga tributaries flashed within minutes.' },
  { id: 'ev-8', date: '2018-09-23', type: 'Flood', district: 'Kullu', location: 'Beas & Parvati', deaths: 1, affected: 22000, lossCr: 310, severity: 'high', summary: 'Post-monsoon extreme event; record September discharge at Bhuntar.' },
  { id: 'ev-9', date: '2017-08-13', type: 'Landslide', district: 'Mandi', location: 'Kotropi (NH-154)', deaths: 46, affected: 600, lossCr: 38, severity: 'severe', summary: 'Massive slope failure buried two buses; among the deadliest slides in state history.' },
  { id: 'ev-10', date: '2015-06-21', type: 'Flash Flood', district: 'Chamba', location: 'Ravi tributary', deaths: 4, affected: 2600, lossCr: 52, severity: 'moderate', summary: 'Pre-monsoon convective burst; footbridges and irrigation kuhls damaged.' },
]

/* --------------------------------- Reports ------------------------------- */

export interface ReportItem {
  id: string
  title: string
  type: 'Situation' | 'Forecast' | 'Post-event' | 'Research'
  period: string
  generatedAt: string
  pages: number
  status: 'ready' | 'generating' | 'scheduled'
}

export const REPORTS: ReportItem[] = [
  { id: 'rp-1', title: 'Daily Situation Report — State-wide', type: 'Situation', period: '15 Jul 2026', generatedAt: '06:00 IST', pages: 12, status: 'ready' },
  { id: 'rp-2', title: '72h Hazard Outlook — Beas Basin', type: 'Forecast', period: '15–18 Jul 2026', generatedAt: '05:30 IST', pages: 8, status: 'ready' },
  { id: 'rp-3', title: 'Cloudburst Watch Bulletin — Kullu', type: 'Forecast', period: 'Next 6 hours', generatedAt: '06:40 IST', pages: 3, status: 'ready' },
  { id: 'rp-4', title: 'Weekly Model Performance Digest', type: 'Research', period: 'Week 28, 2026', generatedAt: '—', pages: 16, status: 'generating' },
  { id: 'rp-5', title: 'Post-event Analysis — Samej Cloudburst', type: 'Post-event', period: 'Aug 2024', generatedAt: '12 Jul 2026', pages: 42, status: 'ready' },
  { id: 'rp-6', title: 'Monthly Rainfall Verification', type: 'Research', period: 'Jun 2026', generatedAt: '01 Jul 2026', pages: 22, status: 'ready' },
  { id: 'rp-7', title: 'Infrastructure Exposure Assessment', type: 'Research', period: 'Q2 2026', generatedAt: '—', pages: 0, status: 'scheduled' },
]

/* ------------------------------ Notifications ---------------------------- */

export interface NotificationItem {
  id: string
  title: string
  body: string
  category: 'alert' | 'system' | 'model' | 'report'
  time: string
  read: boolean
}

export const NOTIFICATIONS: NotificationItem[] = [
  { id: 'nt-1', title: 'Severe cloudburst watch issued', body: 'Kullu district — probability 91% within 6 hours. Alert AL-1 dispatched to district EOC.', category: 'alert', time: '12 min ago', read: false },
  { id: 'nt-2', title: 'LSTM training epoch 34/40 complete', body: 'Validation loss 0.412, improving. ETA 26 minutes on gpu-node-02.', category: 'model', time: '38 min ago', read: false },
  { id: 'nt-3', title: 'Beas gauge exceeded 80% capacity', body: 'Pandoh station reading 8.4m against danger level 10.2m and rising.', category: 'alert', time: '1 h ago', read: false },
  { id: 'nt-4', title: 'Daily situation report ready', body: 'SITREP for 15 Jul 2026 generated and shared with 14 subscribers.', category: 'report', time: '2 h ago', read: true },
  { id: 'nt-5', title: 'IMERG ingestion completed', body: '48 granules processed, 0 gaps. Latency 3h 42m from observation.', category: 'system', time: '3 h ago', read: true },
  { id: 'nt-6', title: 'New ERA5 monthly archive available', body: 'June 2026 reanalysis published by CDS; collector queued.', category: 'system', time: '6 h ago', read: true },
  { id: 'nt-7', title: 'XGBoost retraining finished', body: 'MAE improved 3.18 → 3.12 with monsoon-2026 features.', category: 'model', time: 'Yesterday', read: true },
]

/* --------------------------------- Admin --------------------------------- */

export interface PlatformUser {
  id: string
  name: string
  email: string
  role: 'Admin' | 'Researcher' | 'Analyst' | 'District Officer' | 'Viewer'
  org: string
  lastActive: string
  status: 'active' | 'invited' | 'suspended'
}

export const PLATFORM_USERS: PlatformUser[] = [
  { id: 'u-1', name: 'Dr. Rajat Sharma', email: 'rajat@iitmandi.ac.in', role: 'Admin', org: 'IIT Mandi', lastActive: '2 min ago', status: 'active' },
  { id: 'u-2', name: 'Ananya Verma', email: 'ananya@iitmandi.ac.in', role: 'Researcher', org: 'IIT Mandi', lastActive: '14 min ago', status: 'active' },
  { id: 'u-3', name: 'Vikram Negi', email: 'vikram.negi@hp.gov.in', role: 'District Officer', org: 'DDMA Kullu', lastActive: '1 h ago', status: 'active' },
  { id: 'u-4', name: 'Priya Thakur', email: 'priya.thakur@hp.gov.in', role: 'District Officer', org: 'DDMA Mandi', lastActive: '3 h ago', status: 'active' },
  { id: 'u-5', name: 'Arjun Mehta', email: 'arjun@iitmandi.ac.in', role: 'Analyst', org: 'IIT Mandi', lastActive: 'Yesterday', status: 'active' },
  { id: 'u-6', name: 'Sneha Kapoor', email: 'sneha.kapoor@hpsdma.nic.in', role: 'Analyst', org: 'HPSDMA', lastActive: '2 days ago', status: 'active' },
  { id: 'u-7', name: 'Rohit Chauhan', email: 'rohit.c@hpsdma.nic.in', role: 'Viewer', org: 'HPSDMA', lastActive: '—', status: 'invited' },
  { id: 'u-8', name: 'Test Account', email: 'qa@varuna.dev', role: 'Viewer', org: 'Internal', lastActive: '30 days ago', status: 'suspended' },
]

export const SERVICE_HEALTH = [
  { service: 'Ingestion Pipeline', uptime: 99.94, latencyMs: 240, status: 'operational' },
  { service: 'Prediction API', uptime: 99.98, latencyMs: 86, status: 'operational' },
  { service: 'Tile / Map Server', uptime: 99.9, latencyMs: 132, status: 'operational' },
  { service: 'Alert Dispatcher', uptime: 100, latencyMs: 44, status: 'operational' },
  { service: 'Model Training Cluster', uptime: 97.2, latencyMs: 0, status: 'degraded' },
  { service: 'Report Generator', uptime: 99.6, latencyMs: 1840, status: 'operational' },
]

export const API_USAGE = Array.from({ length: 14 }, (_, i) => ({
  day: `Jul ${i + 2}`,
  requests: Number((42000 + Math.sin(i / 2.2) * 9000 + i * 1200 + Math.random() * 3000).toFixed(0)),
  errors: Number((120 + Math.random() * 180).toFixed(0)),
}))

/* ------------------------------ AI Assistant ----------------------------- */

export const ASSISTANT_SUGGESTIONS = [
  'What is the current flood risk for Mandi district?',
  'Explain why the cloudburst probability for Kullu is 91%',
  'Compare LSTM and XGBoost performance on rainfall prediction',
  'Which infrastructure assets are at risk in the next 24 hours?',
  'Summarize the last 5 years of disaster events in the Beas basin',
]

export const ASSISTANT_CANNED: Record<string, string> = {
  default:
    'Based on the latest model run (06:00 IST), the upper Beas basin shows strong convective development. The Temporal Fusion Transformer ensemble assigns a 91% cloudburst probability to the Kullu–Manali corridor within the next 6 hours, driven primarily by CAPE (2,840 J/kg), 86% soil saturation, and orographic uplift along the Rohtang axis. I recommend reviewing the Alert Centre — a severe watch (AL-1) is already active, and Pandoh dam inflow is rising at +18% per 6h. Would you like a district-level breakdown or the SHAP attribution for this prediction?',
  flood:
    'Current flood risk for Mandi is HIGH. The Beas at Pandoh reads 8.4m against a 10.2m danger mark (82% capacity) with a rising trend of +18% inflow per 6 hours. LSTM routing projects the danger mark could be reached in ~14 hours if upstream rainfall persists. Zonal Hospital Mandi and Victoria Bridge are flagged as severe-risk assets. Evacuation advisories for low-lying markets are recommended per SOP-7.',
  model:
    'On the held-out monsoon test set: XGBoost achieves MAE 3.12mm / R² 0.82 with 1.4ms inference, while LSTM (still training, epoch 34/40) currently reaches MAE 2.86mm / R² 0.85 at 8.4ms inference. LSTM better captures temporal persistence in multi-hour accumulation, whereas XGBoost remains superior for fast, feature-attributed nowcasts. The planned Temporal Fusion Transformer is expected to outperform both (target MAE ≤ 2.3mm) with native uncertainty quantification.',
}

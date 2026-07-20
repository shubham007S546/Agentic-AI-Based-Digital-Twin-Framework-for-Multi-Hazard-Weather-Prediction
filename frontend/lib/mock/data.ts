import type {
  WeatherSnapshot,
  ForecastDay,
  HazardStation,
  RiverGauge,
  ModelMetrics,
  DatasetInfo,
  FeatureImportance,
  PipelineStage,
  AlertItem,
} from '@/types'

export const CURRENT_WEATHER: WeatherSnapshot = {
  temperature: 24.6,
  humidity: 78,
  pressure: 1008.2,
  windSpeed: 14.2,
  windDirection: 'SW',
  rainfall: 12.4,
  dewPoint: 20.1,
  visibility: 8.4,
  uvIndex: 6,
  cloudCover: 72,
  condition: 'Monsoon showers',
  updatedAt: new Date().toISOString(),
}

export const FORECAST_7D: ForecastDay[] = [
  { date: '2026-07-15', day: 'Today', tempMin: 19, tempMax: 27, rainfall: 24.2, rainProbability: 86, humidity: 82, windSpeed: 16, condition: 'Heavy rain' },
  { date: '2026-07-16', day: 'Thu', tempMin: 18, tempMax: 26, rainfall: 38.6, rainProbability: 92, humidity: 88, windSpeed: 18, condition: 'Very heavy rain' },
  { date: '2026-07-17', day: 'Fri', tempMin: 18, tempMax: 25, rainfall: 21.4, rainProbability: 78, humidity: 84, windSpeed: 14, condition: 'Rain' },
  { date: '2026-07-18', day: 'Sat', tempMin: 19, tempMax: 27, rainfall: 8.2, rainProbability: 55, humidity: 76, windSpeed: 11, condition: 'Scattered showers' },
  { date: '2026-07-19', day: 'Sun', tempMin: 20, tempMax: 29, rainfall: 2.1, rainProbability: 30, humidity: 68, windSpeed: 9, condition: 'Partly cloudy' },
  { date: '2026-07-20', day: 'Mon', tempMin: 21, tempMax: 30, rainfall: 4.6, rainProbability: 42, humidity: 71, windSpeed: 10, condition: 'Cloudy' },
  { date: '2026-07-21', day: 'Tue', tempMin: 20, tempMax: 28, rainfall: 15.8, rainProbability: 70, humidity: 79, windSpeed: 13, condition: 'Rain' },
]

export const HOURLY_RAINFALL = Array.from({ length: 24 }, (_, i) => ({
  hour: `${String(i).padStart(2, '0')}:00`,
  rainfall: Number((Math.max(0, Math.sin(i / 3.4) * 8 + Math.cos(i / 1.9) * 4 + 4)).toFixed(1)),
  predicted: Number((Math.max(0, Math.sin(i / 3.2) * 8 + Math.cos(i / 2.1) * 4 + 4.5)).toFixed(1)),
}))

export const MONTHLY_RAINFALL = [
  { month: 'Jan', observed: 84, normal: 92 },
  { month: 'Feb', observed: 108, normal: 96 },
  { month: 'Mar', observed: 121, normal: 110 },
  { month: 'Apr', observed: 74, normal: 68 },
  { month: 'May', observed: 62, normal: 58 },
  { month: 'Jun', observed: 148, normal: 126 },
  { month: 'Jul', observed: 342, normal: 288 },
  { month: 'Aug', observed: 296, normal: 274 },
  { month: 'Sep', observed: 168, normal: 152 },
  { month: 'Oct', observed: 42, normal: 48 },
  { month: 'Nov', observed: 18, normal: 22 },
  { month: 'Dec', observed: 46, normal: 52 },
]

export const HAZARD_STATIONS: HazardStation[] = [
  { id: 'st-1', name: 'Mandi', district: 'Mandi', lat: 31.7084, lng: 76.9319, risk: 'high', probability: 74, metric: 128 },
  { id: 'st-2', name: 'Kullu', district: 'Kullu', lat: 31.9576, lng: 77.1095, risk: 'severe', probability: 88, metric: 164 },
  { id: 'st-3', name: 'Manali', district: 'Kullu', lat: 32.2396, lng: 77.1887, risk: 'severe', probability: 91, metric: 182 },
  { id: 'st-4', name: 'Shimla', district: 'Shimla', lat: 31.1048, lng: 77.1734, risk: 'moderate', probability: 52, metric: 86 },
  { id: 'st-5', name: 'Dharamshala', district: 'Kangra', lat: 32.219, lng: 76.3234, risk: 'high', probability: 69, metric: 142 },
  { id: 'st-6', name: 'Chamba', district: 'Chamba', lat: 32.5534, lng: 76.1258, risk: 'moderate', probability: 46, metric: 74 },
  { id: 'st-7', name: 'Solan', district: 'Solan', lat: 30.9045, lng: 77.0967, risk: 'low', probability: 24, metric: 42 },
  { id: 'st-8', name: 'Una', district: 'Una', lat: 31.4685, lng: 76.2708, risk: 'low', probability: 18, metric: 31 },
  { id: 'st-9', name: 'Keylong', district: 'Lahaul & Spiti', lat: 32.5717, lng: 77.0323, risk: 'moderate', probability: 41, metric: 58 },
  { id: 'st-10', name: 'Rampur', district: 'Shimla', lat: 31.4496, lng: 77.6305, risk: 'high', probability: 66, metric: 118 },
]

export const RIVER_GAUGES: RiverGauge[] = [
  { id: 'rv-1', river: 'Beas', station: 'Pandoh Dam', level: 8.4, dangerLevel: 10.2, discharge: 1240, trend: 'rising' },
  { id: 'rv-2', river: 'Beas', station: 'Manali', level: 4.2, dangerLevel: 5.5, discharge: 620, trend: 'rising' },
  { id: 'rv-3', river: 'Sutlej', station: 'Rampur', level: 6.1, dangerLevel: 9.0, discharge: 980, trend: 'steady' },
  { id: 'rv-4', river: 'Ravi', station: 'Chamba', level: 3.8, dangerLevel: 6.4, discharge: 410, trend: 'falling' },
  { id: 'rv-5', river: 'Parvati', station: 'Bhuntar', level: 3.1, dangerLevel: 4.0, discharge: 356, trend: 'rising' },
]

export const MODEL_METRICS: ModelMetrics[] = [
  { name: 'Linear Regression', category: 'ml', mae: 4.82, rmse: 7.14, r2: 0.61, mape: 22.4, precision: 0.64, recall: 0.58, f1: 0.61, mcc: 0.42, trainingTime: 0.4, inferenceMs: 0.2, params: '1.2K', status: 'trained' },
  { name: 'Decision Tree', category: 'ml', mae: 4.21, rmse: 6.52, r2: 0.68, mape: 19.8, precision: 0.69, recall: 0.66, f1: 0.67, mcc: 0.49, trainingTime: 1.2, inferenceMs: 0.3, params: '8.4K', status: 'trained' },
  { name: 'Random Forest', category: 'ml', mae: 3.44, rmse: 5.38, r2: 0.78, mape: 15.6, precision: 0.78, recall: 0.74, f1: 0.76, mcc: 0.61, trainingTime: 8.6, inferenceMs: 2.1, params: '2.4M', status: 'trained' },
  { name: 'XGBoost', category: 'ml', mae: 3.12, rmse: 4.96, r2: 0.82, mape: 13.9, precision: 0.81, recall: 0.78, f1: 0.79, mcc: 0.66, trainingTime: 6.4, inferenceMs: 1.4, params: '1.8M', status: 'trained' },
  { name: 'LightGBM', category: 'ml', mae: 3.18, rmse: 5.02, r2: 0.81, mape: 14.2, precision: 0.8, recall: 0.77, f1: 0.78, mcc: 0.65, trainingTime: 3.8, inferenceMs: 0.9, params: '1.6M', status: 'trained' },
  { name: 'CatBoost', category: 'ml', mae: 3.15, rmse: 4.99, r2: 0.82, mape: 14.0, precision: 0.81, recall: 0.77, f1: 0.79, mcc: 0.65, trainingTime: 9.2, inferenceMs: 1.2, params: '2.1M', status: 'trained' },
  { name: 'LSTM', category: 'dl', mae: 2.86, rmse: 4.52, r2: 0.85, mape: 12.4, precision: 0.83, recall: 0.81, f1: 0.82, mcc: 0.7, trainingTime: 42, inferenceMs: 8.4, params: '4.8M', status: 'training' },
  { name: 'GRU', category: 'dl', mae: 2.91, rmse: 4.6, r2: 0.84, mape: 12.8, precision: 0.82, recall: 0.8, f1: 0.81, mcc: 0.69, trainingTime: 36, inferenceMs: 7.2, params: '3.9M', status: 'training' },
  { name: 'CNN-LSTM', category: 'dl', mae: 2.74, rmse: 4.38, r2: 0.86, mape: 11.9, precision: 0.84, recall: 0.82, f1: 0.83, mcc: 0.72, trainingTime: 58, inferenceMs: 10.6, params: '6.2M', status: 'planned' },
  { name: 'TCN', category: 'dl', mae: 2.79, rmse: 4.44, r2: 0.86, mape: 12.1, precision: 0.84, recall: 0.81, f1: 0.82, mcc: 0.71, trainingTime: 31, inferenceMs: 5.8, params: '3.2M', status: 'planned' },
  { name: 'Transformer', category: 'transformer', mae: 2.52, rmse: 4.08, r2: 0.88, mape: 10.8, precision: 0.86, recall: 0.84, f1: 0.85, mcc: 0.75, trainingTime: 96, inferenceMs: 14.2, params: '12.4M', status: 'planned' },
  { name: 'Informer', category: 'transformer', mae: 2.46, rmse: 3.98, r2: 0.89, mape: 10.4, precision: 0.87, recall: 0.85, f1: 0.86, mcc: 0.77, trainingTime: 88, inferenceMs: 11.8, params: '10.8M', status: 'planned' },
  { name: 'Autoformer', category: 'transformer', mae: 2.41, rmse: 3.92, r2: 0.89, mape: 10.1, precision: 0.87, recall: 0.86, f1: 0.86, mcc: 0.77, trainingTime: 92, inferenceMs: 12.4, params: '11.2M', status: 'planned' },
  { name: 'Temporal Fusion Transformer', category: 'transformer', mae: 2.28, rmse: 3.74, r2: 0.91, mape: 9.4, precision: 0.89, recall: 0.88, f1: 0.88, mcc: 0.8, trainingTime: 124, inferenceMs: 16.8, params: '18.6M', status: 'planned' },
]

export const DATASETS: DatasetInfo[] = [
  { name: 'Open-Meteo Hourly', source: 'Open-Meteo API', category: 'Weather', records: '4.2M', sizeMB: 862, resolution: 'Hourly / 11km', status: 'collected', updatedAt: '2026-07-14' },
  { name: 'ERA5 Reanalysis', source: 'ECMWF CDS', category: 'Weather', records: '8.6M', sizeMB: 2140, resolution: 'Hourly / 31km', status: 'collected', updatedAt: '2026-07-12' },
  { name: 'ERA5-Land', source: 'ECMWF CDS', category: 'Weather', records: '6.1M', sizeMB: 1680, resolution: 'Hourly / 9km', status: 'collected', updatedAt: '2026-07-12' },
  { name: 'NASA GPM IMERG', source: 'NASA GES DISC', category: 'Precipitation', records: '2.8M', sizeMB: 940, resolution: '30min / 10km', status: 'collected', updatedAt: '2026-07-13' },
  { name: 'MODIS LST & Cloud', source: 'NASA LP DAAC', category: 'Satellite', records: '1.4M', sizeMB: 720, resolution: 'Daily / 1km', status: 'collected', updatedAt: '2026-07-10' },
  { name: 'NDVI Time Series', source: 'MODIS / Sentinel-2', category: 'Vegetation', records: '860K', sizeMB: 480, resolution: '16-day / 250m', status: 'collected', updatedAt: '2026-07-08' },
  { name: 'Climate Indices', source: 'NOAA / IMD', category: 'Climate', records: '42K', sizeMB: 12, resolution: 'Monthly', status: 'collected', updatedAt: '2026-07-05' },
  { name: 'Census 2011/2021', source: 'Census of India', category: 'Population', records: '128K', sizeMB: 64, resolution: 'Village level', status: 'collected', updatedAt: '2026-06-28' },
  { name: 'Hydrology Network', source: 'CWC / WRIS', category: 'Hydrology', records: '96K', sizeMB: 148, resolution: 'Station level', status: 'collected', updatedAt: '2026-07-11' },
  { name: 'Infrastructure GIS', source: 'OSM / State GIS', category: 'Infrastructure', records: '214K', sizeMB: 320, resolution: 'Asset level', status: 'validating', updatedAt: '2026-07-09' },
  { name: 'SRTM / ALOS DEM', source: 'NASA / JAXA', category: 'Terrain', records: '18M cells', sizeMB: 1240, resolution: '30m', status: 'collected', updatedAt: '2026-06-20' },
  { name: 'HPSDMA Disaster History', source: 'HPSDMA', category: 'Disasters', records: '8.4K', sizeMB: 6, resolution: 'Event level', status: 'collected', updatedAt: '2026-07-01' },
  { name: 'ReliefWeb Reports', source: 'UN OCHA', category: 'Disasters', records: '3.1K', sizeMB: 22, resolution: 'Event level', status: 'processing', updatedAt: '2026-07-06' },
  { name: 'Data.gov.in Records', source: 'Data.gov.in', category: 'Misc', records: '52K', sizeMB: 84, resolution: 'District level', status: 'collected', updatedAt: '2026-06-30' },
]

export const FEATURE_IMPORTANCE: FeatureImportance[] = [
  { feature: 'Rainfall (t-1h)', importance: 0.182, shap: 0.164 },
  { feature: 'GPM Precipitation', importance: 0.148, shap: 0.152 },
  { feature: 'Relative Humidity', importance: 0.121, shap: 0.118 },
  { feature: 'CAPE', importance: 0.104, shap: 0.112 },
  { feature: 'Surface Pressure Δ', importance: 0.092, shap: 0.088 },
  { feature: 'Cloud Cover (High)', importance: 0.078, shap: 0.081 },
  { feature: 'Elevation', importance: 0.066, shap: 0.058 },
  { feature: 'Slope', importance: 0.054, shap: 0.049 },
  { feature: 'NDVI', importance: 0.048, shap: 0.044 },
  { feature: 'Wind Speed 850hPa', importance: 0.042, shap: 0.046 },
  { feature: 'Soil Moisture', importance: 0.038, shap: 0.042 },
  { feature: 'Monsoon Index', importance: 0.027, shap: 0.031 },
]

export const PIPELINE_STAGES: PipelineStage[] = [
  { name: 'Dataset Collection', status: 'complete', description: '17 collectors across weather, satellite, hydrology, terrain and disaster records' },
  { name: 'Data Validation', status: 'complete', description: 'Schema checks, gap detection, physical range validation and QC flags' },
  { name: 'Feature Engineering', status: 'complete', description: '312 engineered features: lags, rolling stats, terrain derivatives, indices' },
  { name: 'Master Dataset', status: 'complete', description: 'Unified spatio-temporal dataset merged across all sources' },
  { name: 'Machine Learning', status: 'complete', description: 'Six classical models trained with hyperparameter tuning' },
  { name: 'Deep Learning', status: 'active', description: 'LSTM and GRU training in progress; CNN-LSTM and TCN queued' },
  { name: 'Transformer Models', status: 'upcoming', description: 'Transformer, Informer, Autoformer benchmarking' },
  { name: 'Temporal Fusion Transformer', status: 'upcoming', description: 'Multi-horizon probabilistic forecasting backbone' },
  { name: 'Explainable AI', status: 'upcoming', description: 'SHAP, attention maps and variable-importance analysis' },
  { name: 'Agentic AI', status: 'upcoming', description: 'Autonomous monitoring, reasoning and alerting agents' },
  { name: 'Digital Twin', status: 'upcoming', description: 'Live virtual replica of terrain, rivers and infrastructure' },
  { name: 'Decision Support System', status: 'upcoming', description: 'Risk scenarios and resource planning for authorities' },
  { name: 'Early Warning Platform', status: 'upcoming', description: 'Village-level alerts with lead times up to 72 hours' },
]

export const ALERTS: AlertItem[] = [
  { id: 'al-1', title: 'Cloudburst watch', district: 'Kullu', severity: 'severe', type: 'Cloudburst', issuedAt: '2026-07-15T06:40:00Z', message: 'Convective cells intensifying over upper Beas basin. Probability 91% within 6 hours.' },
  { id: 'al-2', title: 'Flood warning — Beas', district: 'Mandi', severity: 'high', type: 'Flood', issuedAt: '2026-07-15T05:10:00Z', message: 'Pandoh dam inflow rising sharply. Level 8.4m against danger mark 10.2m.' },
  { id: 'al-3', title: 'Landslide advisory NH-3', district: 'Mandi', severity: 'high', type: 'Landslide', issuedAt: '2026-07-14T22:30:00Z', message: 'Saturated slopes near Hanogi. Slope stability index below threshold.' },
  { id: 'al-4', title: 'Heavy rainfall alert', district: 'Kangra', severity: 'moderate', type: 'Rainfall', issuedAt: '2026-07-14T18:00:00Z', message: 'IMD orange alert. Expected 24h accumulation 60–110mm.' },
]

export const RISK_COLORS: Record<string, string> = {
  low: 'oklch(0.75 0.15 160)',
  moderate: 'oklch(0.8 0.15 80)',
  high: 'oklch(0.72 0.17 55)',
  severe: 'oklch(0.64 0.2 25)',
}

export const TRAINING_HISTORY = Array.from({ length: 40 }, (_, i) => ({
  epoch: i + 1,
  trainLoss: Number((2.4 * Math.exp(-i / 9) + 0.32 + Math.random() * 0.04).toFixed(3)),
  valLoss: Number((2.6 * Math.exp(-i / 10) + 0.38 + Math.random() * 0.06).toFixed(3)),
}))

export const PREDICTION_TIMELINE = Array.from({ length: 48 }, (_, i) => {
  const actual = Math.max(0, Math.sin(i / 5) * 12 + Math.cos(i / 2.6) * 5 + 8)
  return {
    hour: `+${i}h`,
    actual: i < 24 ? Number(actual.toFixed(1)) : null,
    predicted: Number((actual + Math.sin(i / 3) * 1.6).toFixed(1)),
    upper: Number((actual + 4 + i * 0.12).toFixed(1)),
    lower: Number(Math.max(0, actual - 4 - i * 0.12).toFixed(1)),
  }
})

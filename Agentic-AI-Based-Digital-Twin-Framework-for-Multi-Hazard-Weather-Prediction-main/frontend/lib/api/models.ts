/**
 * lib/api/models.ts
 * Dynamic model registry & benchmark metrics API integration.
 */
import { apiFetch, fetchWithFallback } from './client'
import { MODEL_METRICS } from '@/lib/mock/data'

export interface ModelMetricItem {
  name: string
  category: 'ml' | 'dl' | 'transformer'
  family?: string
  mae: number
  rmse: number
  r2: number
  f1: number
  mcc: number
  inferenceMs: number
  params: string
  status: 'trained' | 'training' | 'planned'
  is_champion?: boolean
  file?: string
}

export interface ModelBenchmarkResponse {
  models: ModelMetricItem[]
  champion: string
  best_mae: number
  fastest_inference: number
  total_tracked: number
  trained_count: number
  training_count: number
}

const MOCK_FALLBACK: ModelBenchmarkResponse = {
  models: MODEL_METRICS as ModelMetricItem[],
  champion: 'LightGBM',
  best_mae: 0.176,
  fastest_inference: 0.2,
  total_tracked: MODEL_METRICS.length,
  trained_count: MODEL_METRICS.filter((m) => m.status === 'trained').length,
  training_count: MODEL_METRICS.filter((m) => m.status === 'training').length,
}

export async function getModelBenchmark(): Promise<ModelBenchmarkResponse> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<{ data: ModelBenchmarkResponse }>('/models/benchmark')
      return res.data
    },
    MOCK_FALLBACK,
  )
}

/**
 * lib/api/weather.ts
 * Weather data API calls with mock fallback.
 */
import { apiFetch, fetchWithFallback } from './client'
import {
  CURRENT_WEATHER,
  FORECAST_7D,
  HOURLY_RAINFALL,
  MONTHLY_RAINFALL,
} from '@/lib/mock/data'
import type { WeatherSnapshot, ForecastDay } from '@/types'

interface WeatherResponse {
  data: WeatherSnapshot
}
interface ForecastResponse {
  data: ForecastDay[]
}
interface HourlyResponse {
  data: { hour: string; rainfall: number; predicted: number }[]
}
interface MonthlyResponse {
  data: { month: string; observed: number; normal: number }[]
}

export async function getCurrentWeather(): Promise<WeatherSnapshot> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<WeatherResponse>('/weather/current')
      return res.data
    },
    CURRENT_WEATHER,
  )
}

export async function get7DayForecast(): Promise<ForecastDay[]> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<ForecastResponse>('/weather/forecast?days=7')
      return res.data
    },
    FORECAST_7D,
  )
}

export async function getHourlyRainfall(): Promise<
  { hour: string; rainfall: number; predicted: number }[]
> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<HourlyResponse>('/weather/rainfall/hourly')
      return res.data
    },
    HOURLY_RAINFALL,
  )
}

export async function getMonthlyRainfall(): Promise<
  { month: string; observed: number; normal: number }[]
> {
  return fetchWithFallback(
    async () => {
      const res = await apiFetch<MonthlyResponse>('/weather/rainfall/monthly')
      return res.data
    },
    MONTHLY_RAINFALL,
  )
}

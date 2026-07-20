'use client'

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { FORECAST_7D } from '@/lib/mock/data'

const AXIS = { fontSize: 11, fill: 'oklch(0.68 0.015 250)' }
const GRID = 'oklch(1 0 0 / 8%)'
const TOOLTIP_STYLE = {
  backgroundColor: 'oklch(0.2 0.022 252)',
  border: '1px solid oklch(1 0 0 / 12%)',
  borderRadius: 10,
  fontSize: 12,
  color: 'oklch(0.94 0.01 250)',
}
const C1 = 'oklch(0.78 0.13 205)'
const C2 = 'oklch(0.75 0.15 160)'
const C3 = 'oklch(0.8 0.15 80)'
const C4 = 'oklch(0.64 0.2 25)'

export function ForecastTempChart() {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={FORECAST_7D} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="°" />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="tempMax" name="Max temp" stroke={C3} strokeWidth={2} dot={{ r: 3 }} />
        <Line type="monotone" dataKey="tempMin" name="Min temp" stroke={C1} strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function ForecastRainChart() {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={FORECAST_7D} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="day" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="mm" />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'oklch(1 0 0 / 5%)' }} />
        <Bar dataKey="rainfall" name="Rainfall" radius={[4, 4, 0, 0]}>
          {FORECAST_7D.map((d) => (
            <Cell key={d.date} fill={d.rainfall > 30 ? C4 : d.rainfall > 15 ? C3 : C1} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ProbabilityGauge({ value, label }: { value: number; label: string }) {
  const color = value > 75 ? C4 : value > 50 ? C3 : value > 25 ? C1 : C2
  return (
    <div className="relative flex flex-col items-center">
      <ResponsiveContainer width="100%" height={160}>
        <RadialBarChart
          innerRadius="72%"
          outerRadius="100%"
          startAngle={210}
          endAngle={-30}
          data={[{ value, fill: color }]}
        >
          <RadialBar dataKey="value" cornerRadius={8} background={{ fill: 'oklch(1 0 0 / 8%)' }} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold tabular-nums">{value}%</span>
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1">{label}</span>
      </div>
    </div>
  )
}

export function GenericAreaChart({
  data,
  xKey,
  series,
  unit,
  height = 260,
  interval,
}: {
  data: Record<string, unknown>[]
  xKey: string
  series: { key: string; name: string; color?: string; dashed?: boolean }[]
  unit?: string
  height?: number
  interval?: number
}) {
  const colors = [C1, C2, C3, C4]
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`g-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color ?? colors[i % 4]} stopOpacity={0.35} />
              <stop offset="100%" stopColor={s.color ?? colors[i % 4]} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} interval={interval} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit={unit} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={s.color ?? colors[i % 4]}
            fill={`url(#g-${s.key})`}
            strokeWidth={2}
            strokeDasharray={s.dashed ? '5 4' : undefined}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function GenericBarChart({
  data,
  xKey,
  series,
  unit,
  height = 260,
}: {
  data: Record<string, unknown>[]
  xKey: string
  series: { key: string; name: string; color?: string }[]
  unit?: string
  height?: number
}) {
  const colors = [C1, C2, C3, C4]
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit={unit} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'oklch(1 0 0 / 5%)' }} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color ?? colors[i % 4]} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

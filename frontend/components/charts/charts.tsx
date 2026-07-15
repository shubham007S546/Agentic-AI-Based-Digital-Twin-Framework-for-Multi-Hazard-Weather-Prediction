'use client'

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  HOURLY_RAINFALL,
  MONTHLY_RAINFALL,
  TRAINING_HISTORY,
  PREDICTION_TIMELINE,
  FEATURE_IMPORTANCE,
} from '@/lib/mock/data'

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

export function HourlyRainfallChart() {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={HOURLY_RAINFALL} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="rain" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C1} stopOpacity={0.4} />
            <stop offset="100%" stopColor={C1} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={false} interval={3} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="mm" />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Area type="monotone" dataKey="rainfall" name="Observed" stroke={C1} fill="url(#rain)" strokeWidth={2} />
        <Line type="monotone" dataKey="predicted" name="Predicted" stroke={C3} strokeWidth={1.5} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function MonthlyRainfallChart() {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={MONTHLY_RAINFALL} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="month" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="mm" />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'oklch(1 0 0 / 5%)' }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="observed" name="Observed" fill={C1} radius={[4, 4, 0, 0]} />
        <Bar dataKey="normal" name="Climatological normal" fill="oklch(0.4 0.02 250)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function TrainingHistoryChart() {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={TRAINING_HISTORY} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="epoch" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="trainLoss" name="Train loss" stroke={C1} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="valLoss" name="Validation loss" stroke={C4} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function PredictionTimelineChart() {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={PREDICTION_TIMELINE} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C1} stopOpacity={0.18} />
            <stop offset="100%" stopColor={C1} stopOpacity={0.04} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={false} interval={5} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="mm" />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="upper" name="Upper CI" stroke="none" fill="url(#band)" />
        <Area type="monotone" dataKey="lower" name="Lower CI" stroke="none" fill="oklch(0.16 0.02 250)" />
        <Line type="monotone" dataKey="actual" name="Observed" stroke={C2} strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="predicted" name="TFT prediction" stroke={C1} strokeWidth={2} strokeDasharray="5 4" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function FeatureImportanceChart({ metric = 'shap' }: { metric?: 'shap' | 'importance' }) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart
        data={FEATURE_IMPORTANCE}
        layout="vertical"
        margin={{ top: 4, right: 16, left: 40, bottom: 0 }}
      >
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="feature" tick={{ ...AXIS, fontSize: 10 }} width={110} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'oklch(1 0 0 / 5%)' }} />
        <Bar dataKey={metric} name={metric === 'shap' ? 'Mean |SHAP|' : 'Importance'} fill={C1} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ModelCompareChart({
  data,
  metric,
  label,
}: {
  data: { name: string; value: number }[]
  metric: string
  label: string
}) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 60, bottom: 0 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="name" tick={{ ...AXIS, fontSize: 10 }} width={140} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'oklch(1 0 0 / 5%)' }} />
        <Bar dataKey="value" name={label} fill={metric === 'r2' ? C2 : C1} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

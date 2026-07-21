import type { Metadata } from 'next'
import {
  CloudRain,
  Droplets,
  Thermometer,
  Gauge,
  Wind,
  Eye,
  Sun,
  Cloud,
} from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { HourlyRainfallChart } from '@/components/charts/charts'
import { CURRENT_WEATHER, HAZARD_STATIONS } from '@/lib/mock/data'
import { RiskBadge } from '@/components/shared/risk-badge'

export const metadata: Metadata = {
  title: 'Live Weather | VARUNA',
  description: 'Real-time atmospheric conditions across Himachal Pradesh stations.',
}

export default function WeatherPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Live Weather"
        description="Real-time atmospheric conditions fused from Open-Meteo, ERA5 and station telemetry. Updated every 10 minutes."
      />

      <section aria-label="Current conditions" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Temperature" value={CURRENT_WEATHER.temperature} unit="°C" icon={Thermometer} sub={CURRENT_WEATHER.condition} />
        <StatCard label="Rainfall (1h)" value={CURRENT_WEATHER.rainfall} unit="mm" icon={CloudRain} sub="Monsoon active" tone="warning" />
        <StatCard label="Humidity" value={CURRENT_WEATHER.humidity} unit="%" icon={Droplets} sub={`Dew point ${CURRENT_WEATHER.dewPoint}°C`} />
        <StatCard label="Pressure" value={CURRENT_WEATHER.pressure} unit="hPa" icon={Gauge} sub="Falling trend" tone="warning" />
        <StatCard label="Wind" value={CURRENT_WEATHER.windSpeed} unit="km/h" icon={Wind} sub={`From ${CURRENT_WEATHER.windDirection}`} />
        <StatCard label="Visibility" value={CURRENT_WEATHER.visibility} unit="km" icon={Eye} sub="Reduced in valleys" />
        <StatCard label="UV Index" value={CURRENT_WEATHER.uvIndex} icon={Sun} sub="Moderate" />
        <StatCard label="Cloud Cover" value={CURRENT_WEATHER.cloudCover} unit="%" icon={Cloud} sub="Convective build-up" tone="warning" />
      </section>

      <GlassCard className="p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-medium">Hourly Rainfall — Observed vs Model</h2>
          <span className="text-[10px] font-mono text-muted-foreground">GPM IMERG · XGBoost</span>
        </div>
        <HourlyRainfallChart />
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-4">Station Network</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-border">
                <th className="pb-2 pr-4 font-medium">Station</th>
                <th className="pb-2 pr-4 font-medium">District</th>
                <th className="pb-2 pr-4 font-medium">24h Rain</th>
                <th className="pb-2 pr-4 font-medium">Probability</th>
                <th className="pb-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {HAZARD_STATIONS.map((st) => (
                <tr key={st.id} className="border-b border-border/50 last:border-0">
                  <td className="py-2.5 pr-4 font-medium">{st.name}</td>
                  <td className="py-2.5 pr-4 text-muted-foreground">{st.district}</td>
                  <td className="py-2.5 pr-4 tabular-nums">{st.metric} mm</td>
                  <td className="py-2.5 pr-4 tabular-nums">{st.probability}%</td>
                  <td className="py-2.5"><RiskBadge risk={st.risk} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  )
}

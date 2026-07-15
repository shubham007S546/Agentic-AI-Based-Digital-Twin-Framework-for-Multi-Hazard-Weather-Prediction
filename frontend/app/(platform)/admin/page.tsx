import type { Metadata } from 'next'
import { Users, Activity, Gauge, ShieldCheck } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { GenericAreaChart } from '@/components/charts/extra-charts'
import { UserTable } from '@/components/admin/user-table'
import { PLATFORM_USERS, SERVICE_HEALTH, API_USAGE } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Administration | VARUNA',
  description: 'Platform administration — users, roles, service health and API usage.',
}

const AUDIT_LOG = [
  { time: '07:12 IST', actor: 'rajat@iitmandi.ac.in', action: 'Approved alert AL-1 for public dispatch' },
  { time: '06:58 IST', actor: 'system', action: 'XGBoost champion model promoted to serving (v2026.07.14)' },
  { time: '06:40 IST', actor: 'model-agent', action: 'Cloudburst watch raised for Kullu (p=0.91)' },
  { time: 'Yesterday', actor: 'ananya@iitmandi.ac.in', action: 'Updated flood threshold for Pandoh gauge (9.8m → 10.2m)' },
  { time: 'Yesterday', actor: 'rajat@iitmandi.ac.in', action: 'Invited rohit.c@hpsdma.nic.in as Viewer' },
  { time: '13 Jul', actor: 'system', action: 'Master dataset v14 published; 3 experiments migrated' },
]

export default function AdminPage() {
  const active = PLATFORM_USERS.filter((u) => u.status === 'active').length
  const degraded = SERVICE_HEALTH.filter((s) => s.status !== 'operational').length

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Administration"
        description="Manage platform users and roles, monitor service health and track every privileged action in the audit log."
      />

      <section aria-label="Admin summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Users" value={PLATFORM_USERS.length} icon={Users} sub={`${active} active`} />
        <StatCard label="Services" value={SERVICE_HEALTH.length} icon={Activity} sub={degraded ? `${degraded} degraded` : 'All operational'} tone={degraded ? 'warning' : 'success'} />
        <StatCard label="API Requests" value="48.2K" unit="/day" icon={Gauge} sub="14-day average" />
        <StatCard label="Uptime (30d)" value="99.9" unit="%" icon={ShieldCheck} sub="Prediction API" tone="success" />
      </section>

      <UserTable />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Service Health</h2>
          <ul className="flex flex-col gap-3">
            {SERVICE_HEALTH.map((s) => (
              <li key={s.service} className="flex items-center gap-3">
                <span
                  className={cn(
                    'size-2 rounded-full shrink-0',
                    s.status === 'operational' ? 'bg-success' : 'bg-warning',
                  )}
                  aria-label={s.status}
                />
                <span className="text-xs font-medium flex-1">{s.service}</span>
                <span className="text-[11px] font-mono tabular-nums text-muted-foreground">
                  {s.latencyMs > 0 ? `${s.latencyMs} ms` : '—'}
                </span>
                <span
                  className={cn(
                    'text-[11px] font-mono tabular-nums w-16 text-right',
                    s.uptime >= 99.5 ? 'text-success' : 'text-warning',
                  )}
                >
                  {s.uptime}%
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-5 pt-4 border-t border-border/50">
            <h3 className="text-xs font-medium mb-3 text-muted-foreground uppercase tracking-wider">API Usage (14 days)</h3>
            <GenericAreaChart
              data={API_USAGE}
              xKey="day"
              series={[
                { key: 'requests', name: 'Requests' },
                { key: 'errors', name: 'Errors' },
              ]}
              height={200}
            />
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <h2 className="text-sm font-medium mb-4">Audit Log</h2>
          <ol className="flex flex-col">
            {AUDIT_LOG.map((entry, i) => (
              <li key={`${entry.time}-${i}`} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="size-2 rounded-full bg-primary/60 shrink-0 mt-1.5" aria-hidden="true" />
                  {i < AUDIT_LOG.length - 1 && <span className="w-px flex-1 bg-border my-1" />}
                </div>
                <div className="pb-4 min-w-0">
                  <p className="text-xs text-pretty">{entry.action}</p>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {entry.time} · {entry.actor}
                  </span>
                </div>
              </li>
            ))}
          </ol>
        </GlassCard>
      </div>
    </div>
  )
}

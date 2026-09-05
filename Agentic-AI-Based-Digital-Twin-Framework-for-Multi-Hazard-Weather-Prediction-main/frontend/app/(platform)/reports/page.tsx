import type { Metadata } from 'next'
import { FileText, CalendarClock, Users, Clock, Download, Loader2 } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import { GlassCard } from '@/components/shared/glass-card'
import { REPORTS } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

export const metadata: Metadata = {
  title: 'Reports | VARUNA',
  description: 'Generated situation reports, forecast bulletins, post-event analyses and research digests.',
}

const TYPE_STYLES: Record<string, string> = {
  Situation: 'bg-primary/15 text-primary border-primary/30',
  Forecast: 'bg-warning/15 text-warning border-warning/30',
  'Post-event': 'bg-destructive/15 text-destructive border-destructive/30',
  Research: 'bg-success/15 text-success border-success/30',
}

const SCHEDULES = [
  { name: 'Daily Situation Report', cadence: 'Every day, 06:00 IST', recipients: '14 subscribers' },
  { name: '72h Hazard Outlook', cadence: 'Every day, 05:30 IST', recipients: 'District EOCs + SDMA' },
  { name: 'Weekly Model Digest', cadence: 'Mondays, 09:00 IST', recipients: 'Research group' },
  { name: 'Monthly Verification', cadence: '1st of month', recipients: 'IMD liaison + archive' },
]

export default function ReportsPage() {
  const ready = REPORTS.filter((r) => r.status === 'ready').length

  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Reports"
        description="Automatically generated situation reports, forecast bulletins and research digests — rendered from live model outputs and observation feeds."
      />

      <section aria-label="Reports summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Available" value={ready} icon={FileText} sub={`of ${REPORTS.length} tracked reports`} />
        <StatCard label="Scheduled Jobs" value={SCHEDULES.length} icon={CalendarClock} sub="Recurring generation" />
        <StatCard label="Subscribers" value={38} icon={Users} sub="Across all distributions" />
        <StatCard label="Avg Generation" value="1.8" unit="s" icon={Clock} sub="Report render latency" tone="success" />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <GlassCard className="p-5 xl:col-span-2">
          <h2 className="text-sm font-medium mb-4">Report Library</h2>
          <ul className="flex flex-col divide-y divide-border/50">
            {REPORTS.map((r) => (
              <li key={r.id} className="flex items-center gap-4 py-3.5">
                <div className="size-10 rounded-lg bg-secondary flex items-center justify-center shrink-0">
                  <FileText className="size-4 text-primary" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-medium">{r.title}</span>
                    <span
                      className={cn(
                        'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium',
                        TYPE_STYLES[r.type],
                      )}
                    >
                      {r.type}
                    </span>
                  </div>
                  <span className="text-[11px] text-muted-foreground block mt-0.5">
                    {r.period}
                    {r.status === 'ready' && ` · generated ${r.generatedAt} · ${r.pages} pages`}
                  </span>
                </div>
                {r.status === 'ready' ? (
                  <button className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-secondary px-3 py-1.5 text-[11px] font-medium text-foreground hover:border-primary/40 transition-colors shrink-0">
                    <Download className="size-3.5" aria-hidden="true" />
                    PDF
                  </button>
                ) : r.status === 'generating' ? (
                  <span className="inline-flex items-center gap-1.5 text-[11px] text-warning shrink-0">
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                    Generating
                  </span>
                ) : (
                  <span className="text-[11px] text-muted-foreground shrink-0">Scheduled</span>
                )}
              </li>
            ))}
          </ul>
        </GlassCard>

        <div className="flex flex-col gap-4">
          <GlassCard className="p-5">
            <h2 className="text-sm font-medium mb-3">Generation Schedule</h2>
            <ul className="flex flex-col gap-3">
              {SCHEDULES.map((s) => (
                <li key={s.name} className="rounded-lg bg-secondary/50 border border-border p-3">
                  <span className="text-xs font-medium block">{s.name}</span>
                  <span className="text-[10px] text-muted-foreground block mt-0.5 font-mono">{s.cadence}</span>
                  <span className="text-[10px] text-muted-foreground">{s.recipients}</span>
                </li>
              ))}
            </ul>
          </GlassCard>

          <GlassCard className="p-5">
            <h2 className="text-sm font-medium mb-3">Report Contents</h2>
            <ul className="flex flex-col gap-2 text-xs text-muted-foreground">
              {[
                'District-wise hazard probabilities with confidence intervals',
                'Gauge levels vs danger marks with 24h trend',
                'Model verification against latest observations',
                'Infrastructure exposure for elevated-risk zones',
                'Recommended actions mapped to SOP references',
              ].map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="size-1 rounded-full bg-primary mt-1.5 shrink-0" aria-hidden="true" />
                  <span className="text-pretty">{item}</span>
                </li>
              ))}
            </ul>
          </GlassCard>
        </div>
      </div>
    </div>
  )
}

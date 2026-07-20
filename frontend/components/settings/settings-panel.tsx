'use client'

import { useState } from 'react'
import { Copy, KeyRound, RefreshCcw } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { cn } from '@/lib/utils'

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-5 w-9 rounded-full transition-colors shrink-0',
        checked ? 'bg-primary' : 'bg-secondary border border-border',
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 size-4 rounded-full bg-background shadow transition-transform',
          checked ? 'translate-x-4' : 'translate-x-0.5',
        )}
      />
    </button>
  )
}

function SettingRow({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-border/50 last:border-0">
      <div className="min-w-0">
        <p className="text-xs font-medium">{title}</p>
        {description && <p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export function SettingsPanel() {
  const [notif, setNotif] = useState({
    severeAlerts: true,
    dailyDigest: true,
    modelRuns: false,
    smsCritical: true,
    emailReports: true,
  })
  const [prefs, setPrefs] = useState({
    autoRefresh: true,
    animations: true,
    compactSidebar: false,
  })
  const [units, setUnits] = useState<'metric' | 'imperial'>('metric')
  const [refreshInterval, setRefreshInterval] = useState('60')
  const [floodThreshold, setFloodThreshold] = useState('10.2')
  const [cloudburstThreshold, setCloudburstThreshold] = useState('0.85')
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)

  const apiKey = 'vrn_live_9f3a...c21e'

  function copyKey() {
    navigator.clipboard?.writeText(apiKey).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function save() {
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-1">Notifications</h2>
        <p className="text-xs text-muted-foreground mb-2">
          Choose how you want to be informed about hazards and platform activity.
        </p>
        <SettingRow title="Severe hazard alerts" description="Push notification the moment a severe alert is raised">
          <Toggle
            checked={notif.severeAlerts}
            onChange={(v) => setNotif({ ...notif, severeAlerts: v })}
            label="Severe hazard alerts"
          />
        </SettingRow>
        <SettingRow title="Daily risk digest" description="Summary of district risk levels every morning at 06:00 IST">
          <Toggle
            checked={notif.dailyDigest}
            onChange={(v) => setNotif({ ...notif, dailyDigest: v })}
            label="Daily risk digest"
          />
        </SettingRow>
        <SettingRow title="Model training runs" description="Notify when a training run completes or fails">
          <Toggle
            checked={notif.modelRuns}
            onChange={(v) => setNotif({ ...notif, modelRuns: v })}
            label="Model training runs"
          />
        </SettingRow>
        <SettingRow title="SMS for critical events" description="Fallback SMS when a cloudburst or flood warning is issued">
          <Toggle
            checked={notif.smsCritical}
            onChange={(v) => setNotif({ ...notif, smsCritical: v })}
            label="SMS for critical events"
          />
        </SettingRow>
        <SettingRow title="Weekly email reports" description="Situation report PDF delivered every Monday">
          <Toggle
            checked={notif.emailReports}
            onChange={(v) => setNotif({ ...notif, emailReports: v })}
            label="Weekly email reports"
          />
        </SettingRow>
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-1">Alert Thresholds</h2>
        <p className="text-xs text-muted-foreground mb-2">
          Region-specific trigger levels used by the alert dispatcher.
        </p>
        <SettingRow title="Flood gauge threshold" description="Pandoh gauge danger level (metres)">
          <input
            type="number"
            step="0.1"
            value={floodThreshold}
            onChange={(e) => setFloodThreshold(e.target.value)}
            aria-label="Flood gauge threshold in metres"
            className="w-24 rounded-lg bg-secondary border border-border px-3 py-1.5 text-xs text-right font-mono outline-none focus:ring-2 focus:ring-primary/40"
          />
        </SettingRow>
        <SettingRow title="Cloudburst probability" description="Minimum model probability to raise a watch">
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={cloudburstThreshold}
            onChange={(e) => setCloudburstThreshold(e.target.value)}
            aria-label="Cloudburst probability threshold"
            className="w-24 rounded-lg bg-secondary border border-border px-3 py-1.5 text-xs text-right font-mono outline-none focus:ring-2 focus:ring-primary/40"
          />
        </SettingRow>
        <SettingRow title="Data refresh interval" description="How often live dashboards poll for new data">
          <select
            value={refreshInterval}
            onChange={(e) => setRefreshInterval(e.target.value)}
            aria-label="Data refresh interval"
            className="rounded-lg bg-secondary border border-border px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-primary/40"
          >
            <option value="30">30 seconds</option>
            <option value="60">1 minute</option>
            <option value="300">5 minutes</option>
            <option value="900">15 minutes</option>
          </select>
        </SettingRow>
        <SettingRow title="Units" description="Measurement system across all dashboards">
          <div className="flex gap-1">
            {(['metric', 'imperial'] as const).map((u) => (
              <button
                key={u}
                type="button"
                onClick={() => setUnits(u)}
                aria-pressed={units === u}
                className={cn(
                  'px-2.5 py-1 rounded-full border text-[11px] font-medium capitalize transition-colors',
                  units === u
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
                )}
              >
                {u}
              </button>
            ))}
          </div>
        </SettingRow>
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-1">Interface</h2>
        <p className="text-xs text-muted-foreground mb-2">Personalise how the workspace behaves.</p>
        <SettingRow title="Auto-refresh dashboards" description="Keep charts in sync without reloading">
          <Toggle
            checked={prefs.autoRefresh}
            onChange={(v) => setPrefs({ ...prefs, autoRefresh: v })}
            label="Auto-refresh dashboards"
          />
        </SettingRow>
        <SettingRow title="Interface animations" description="Chart transitions and micro-interactions">
          <Toggle
            checked={prefs.animations}
            onChange={(v) => setPrefs({ ...prefs, animations: v })}
            label="Interface animations"
          />
        </SettingRow>
        <SettingRow title="Compact sidebar by default" description="Start with the navigation rail collapsed">
          <Toggle
            checked={prefs.compactSidebar}
            onChange={(v) => setPrefs({ ...prefs, compactSidebar: v })}
            label="Compact sidebar by default"
          />
        </SettingRow>
      </GlassCard>

      <GlassCard className="p-5">
        <h2 className="text-sm font-medium mb-1">API Access</h2>
        <p className="text-xs text-muted-foreground mb-3">
          Use this key to access the VARUNA Prediction API from external systems.
        </p>
        <div className="flex items-center gap-2 rounded-lg bg-secondary border border-border px-3 py-2.5">
          <KeyRound className="size-4 text-primary shrink-0" aria-hidden="true" />
          <code className="text-xs font-mono flex-1 truncate">{apiKey}</code>
          <button
            type="button"
            onClick={copyKey}
            className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Copy API key"
          >
            <Copy className="size-3.5" aria-hidden="true" />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg bg-secondary border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCcw className="size-3.5" aria-hidden="true" />
            Rotate Key
          </button>
          <span className="text-[10px] text-muted-foreground font-mono">Last rotated 12 Jun 2026</span>
        </div>
        <div className="mt-5 pt-4 border-t border-border/50 flex items-center justify-between gap-3">
          <p className="text-[11px] text-muted-foreground">
            Changes apply to your account across all devices.
          </p>
          <button
            type="button"
            onClick={save}
            className="rounded-lg bg-primary text-primary-foreground px-4 py-2 text-xs font-medium hover:opacity-90 transition-opacity shrink-0"
          >
            {saved ? 'Saved' : 'Save Changes'}
          </button>
        </div>
      </GlassCard>
    </div>
  )
}

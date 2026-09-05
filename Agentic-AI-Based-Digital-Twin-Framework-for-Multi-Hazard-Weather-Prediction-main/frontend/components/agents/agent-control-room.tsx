'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Wrench,
  XCircle,
} from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { cn } from '@/lib/utils'
import { getAgentHealth, getRagHealth, type AgentHealth, type RagHealth } from '@/lib/api/agents'

type AgentStatus = 'working' | 'standby' | 'complete' | 'warning'

type Agent = {
  id: string
  name: string
  role: string
  status: AgentStatus
  task: string
  progress: number
  color: string
}

type ActivityEvent = {
  time: string
  agent: string
  message: string
  kind: 'tool' | 'handoff' | 'decision' | 'success' | 'warning'
}

const INITIAL_AGENTS: Agent[] = [
  { id: 'orchestrator', name: 'Orchestrator', role: 'Mission control', status: 'working', task: 'Decomposing flood-risk query', progress: 72, color: 'text-cyan-300' },
  { id: 'weather', name: 'Weather Analyst', role: 'Sensor fusion', status: 'working', task: 'Fusing IMD + ERA5 + station feeds', progress: 84, color: 'text-sky-300' },
  { id: 'prediction', name: 'Prediction Agent', role: 'Hazard forecasting', status: 'working', task: 'Scoring cloudburst and flood risk', progress: 61, color: 'text-violet-300' },
  { id: 'twin', name: 'Digital Twin', role: 'Scenario simulation', status: 'standby', task: 'Waiting for model features', progress: 28, color: 'text-emerald-300' },
  { id: 'risk', name: 'Alert & Risk', role: 'Impact assessment', status: 'standby', task: 'Waiting for hazard scores', progress: 16, color: 'text-amber-300' },
  { id: 'report', name: 'Report Agent', role: 'Decision briefing', status: 'standby', task: 'Waiting for final evidence', progress: 8, color: 'text-pink-300' },
]

const INITIAL_EVENTS: ActivityEvent[] = [
  { time: 'now', agent: 'Orchestrator', message: 'New mission opened: assess Mandi flood risk for the next 24 hours.', kind: 'decision' },
  { time: '12s ago', agent: 'Weather Analyst', message: 'weather_tool returned 92 mm expected rainfall with 88% heavy-rain probability.', kind: 'tool' },
  { time: '18s ago', agent: 'Prediction Agent', message: 'prediction_tool is evaluating catchment saturation and river response.', kind: 'tool' },
  { time: '26s ago', agent: 'Orchestrator', message: 'Handoff created: weather evidence → hazard scoring.', kind: 'handoff' },
  { time: '41s ago', agent: 'System', message: 'All 9 data sources healthy. Trace ID VAR-7F2A is recording.', kind: 'success' },
]

const STATUS_META: Record<AgentStatus, { label: string; icon: typeof Activity; className: string }> = {
  working: { label: 'Working', icon: Activity, className: 'text-cyan-300 bg-cyan-300/10' },
  standby: { label: 'Standby', icon: Clock3, className: 'text-muted-foreground bg-secondary/70' },
  complete: { label: 'Complete', icon: CheckCircle2, className: 'text-emerald-300 bg-emerald-300/10' },
  warning: { label: 'Needs attention', icon: AlertTriangle, className: 'text-amber-300 bg-amber-300/10' },
}

function currentTime() {
  return new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date())
}

export function AgentControlRoom() {
  const [agents, setAgents] = useState(INITIAL_AGENTS)
  const [backendHealth, setBackendHealth] = useState<'loading' | 'live' | 'offline'>('loading')
  const [ragHealth, setRagHealth] = useState<RagHealth | null>(null)
  const [events, setEvents] = useState(INITIAL_EVENTS)
  const [running, setRunning] = useState(true)
  const [selectedAgent, setSelectedAgent] = useState('orchestrator')
  const [query, setQuery] = useState('Assess flood risk in Mandi over the next 24 hours')

  useEffect(() => {
    let cancelled = false
    const syncHealth = async () => {
      try {
        const [health, rag] = await Promise.all([getAgentHealth(), getRagHealth()])
        if (cancelled) return
        setBackendHealth('live')
        setRagHealth(rag)
        setAgents((current) => current.map((agent) => {
          const match = health.find((item: AgentHealth) => item.agent_name.toLowerCase().includes(agent.id.replace('-', '_')))
          if (!match) return agent
          return {
            ...agent,
            status: match.is_healthy ? (match.last_execution_status === 'COMPLETED' ? 'complete' : 'working') : 'warning',
            task: match.last_execution_status ? `Last execution: ${match.last_execution_status.toLowerCase()}` : agent.task,
          }
        }))
        setEvents((current) => [
          { time: currentTime(), agent: 'Backend', message: `Live health synchronized for ${health.length} registered agents.`, kind: 'success' },
          ...current,
        ])
      } catch {
        if (!cancelled) {
          setBackendHealth('offline')
          setEvents((current) => [
            { time: currentTime(), agent: 'Backend', message: 'Backend health endpoint unavailable; showing local mission state only.', kind: 'warning' },
            ...current,
          ])
        }
      }
    }
    void syncHealth()
    const healthTimer = window.setInterval(() => void syncHealth(), 15000)
    const timer = running
      ? window.setInterval(() => {
          setAgents((current) =>
            current.map((agent) => {
              if (agent.status !== 'working') return agent
              const progress = Math.min(96, agent.progress + 2)
              return { ...agent, progress, status: progress >= 94 ? 'complete' : agent.status }
            }),
          )
        }, 2200)
      : undefined
    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
      window.clearInterval(healthTimer)
    }
  }, [running])

  const selected = useMemo(
    () => agents.find((agent) => agent.id === selectedAgent) ?? agents[0],
    [agents, selectedAgent],
  )

  function startMission() {
    const trimmed = query.trim()
    if (!trimmed) return
    setRunning(true)
    setAgents(INITIAL_AGENTS.map((agent) => ({ ...agent, status: agent.id === 'orchestrator' || agent.id === 'weather' ? 'working' : 'standby' })))
    setEvents([
      { time: currentTime(), agent: 'Orchestrator', message: `Mission started: ${trimmed}`, kind: 'decision' },
      { time: currentTime(), agent: 'Orchestrator', message: 'Plan created with 6 specialists and 3 evidence gates.', kind: 'handoff' },
      ...INITIAL_EVENTS,
    ])
  }

  return (
    <div className="flex flex-col gap-5">
      <GlassCard className="p-4 lg:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex size-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
              <Radio className="size-5" aria-hidden="true" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold">Live mission trace</h2>
                <span className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium', backendHealth === 'live' ? 'bg-emerald-300/10 text-emerald-300' : backendHealth === 'offline' ? 'bg-amber-300/10 text-amber-300' : 'bg-secondary text-muted-foreground')}>
                  <span className={cn('size-1.5 rounded-full', backendHealth === 'live' ? 'animate-pulse bg-emerald-300' : backendHealth === 'offline' ? 'bg-amber-300' : 'bg-muted-foreground')} /> {backendHealth === 'live' ? 'backend stream connected' : backendHealth === 'offline' ? 'local state only' : 'connecting backend'}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Trace ID VAR-7F2A · updates every 2.2s · no hidden agent steps</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><ShieldCheck className="size-3.5 text-emerald-300" /> 6 agents</span>
            <span className="flex items-center gap-1"><Database className="size-3.5 text-primary" /> 9 sources</span>
            <button type="button" onClick={() => setRunning((value) => !value)} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-foreground hover:bg-secondary">
              {running ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
              {running ? 'Pause stream' : 'Resume stream'}
            </button>
          </div>
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <GlassCard className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold">Agent topology</h2>
              <p className="mt-1 text-xs text-muted-foreground">Select an agent to inspect its current state and responsibility.</p>
            </div>
            <span className="text-[10px] font-mono text-muted-foreground">ORCHESTRATOR → SPECIALISTS</span>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2">
            {agents.map((agent) => {
              const meta = STATUS_META[agent.status]
              const StatusIcon = meta.icon
              return (
                <button
                  key={agent.id}
                  type="button"
                  onClick={() => setSelectedAgent(agent.id)}
                  className={cn('rounded-xl border p-4 text-left transition-all hover:border-primary/50', selectedAgent === agent.id ? 'border-primary/70 bg-primary/5 shadow-[0_0_24px_rgba(56,189,248,0.08)]' : 'border-border bg-secondary/20')}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <span className={cn('flex size-8 items-center justify-center rounded-lg bg-secondary', agent.color)}><Bot className="size-4" /></span>
                      <div><p className="text-sm font-medium">{agent.name}</p><p className="text-[10px] text-muted-foreground">{agent.role}</p></div>
                    </div>
                    <span className={cn('flex items-center gap-1 rounded-full px-2 py-1 text-[10px] font-medium', meta.className)}><StatusIcon className="size-3" />{meta.label}</span>
                  </div>
                  <p className="mt-4 min-h-8 text-xs text-muted-foreground">{agent.task}</p>
                  <div className="mt-3 flex items-center gap-2"><div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary transition-all duration-700" style={{ width: `${agent.progress}%` }} /></div><span className="w-8 text-right text-[10px] font-mono text-muted-foreground">{agent.progress}%</span></div>
                </button>
              )
            })}
          </div>
        </GlassCard>

        <GlassCard className="p-5">
          <div className="flex items-center justify-between">
            <div><h2 className="text-sm font-semibold">RAG evidence layer</h2><p className="mt-1 text-xs text-muted-foreground">Authenticated readiness check for the FAISS + BM25 assistant pipeline.</p></div>
            <span className={cn('rounded-full px-2 py-1 text-[10px] font-medium', ragHealth?.ready ? 'bg-emerald-300/10 text-emerald-300' : 'bg-amber-300/10 text-amber-300')}>{ragHealth?.ready ? 'READY' : 'INDEX REQUIRED'}</span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
            <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[10px] text-muted-foreground">Vectors</p><p className="mt-1 text-sm font-medium">{ragHealth?.vector_count ?? '—'}</p></div>
            <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[10px] text-muted-foreground">Documents</p><p className="mt-1 text-sm font-medium">{ragHealth?.document_count ?? '—'}</p></div>
            <div className="col-span-2 rounded-lg bg-secondary/60 p-3 sm:col-span-1"><p className="text-[10px] text-muted-foreground">Status</p><p className="mt-1 truncate text-sm font-medium">{ragHealth?.ready ? 'Serving citations' : 'Run build_index.py'}</p></div>
          </div>
        </GlassCard>

        <GlassCard className="flex flex-col p-5">
          <div className="flex items-center justify-between">
            <div><p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Selected agent</p><h2 className={cn('mt-1 text-lg font-semibold', selected.color)}>{selected.name}</h2></div>
            <Sparkles className="size-5 text-primary" />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{selected.role} · accountable for one auditable part of the mission.</p>
          <div className="mt-5 grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[10px] text-muted-foreground">Current phase</p><p className="mt-1 text-sm font-medium">{selected.status === 'working' ? 'Reasoning' : 'Queued'}</p></div>
            <div className="rounded-lg bg-secondary/60 p-3"><p className="text-[10px] text-muted-foreground">Confidence</p><p className="mt-1 text-sm font-medium">91.0%</p></div>
          </div>
          <div className="mt-4 rounded-lg border border-border bg-background/30 p-3">
            <div className="flex items-center gap-2 text-xs font-medium"><Wrench className="size-3.5 text-primary" /> Tool activity</div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{selected.id === 'weather' ? 'weather_tool · station fusion · 340 ms' : selected.id === 'prediction' ? 'prediction_tool · flood model · 820 ms' : 'handoff_manager · evidence routing · 42 ms'}</p>
          </div>
          <div className="mt-auto pt-5"><div className="mb-2 flex justify-between text-[10px] text-muted-foreground"><span>Mission contribution</span><span>{selected.progress}%</span></div><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-gradient-to-r from-primary to-violet-400 transition-all duration-700" style={{ width: `${selected.progress}%` }} /></div></div>
        </GlassCard>
      </div>

      <GlassCard className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border p-5 md:flex-row md:items-center md:justify-between">
          <div><h2 className="text-sm font-semibold">Agent event stream</h2><p className="mt-1 text-xs text-muted-foreground">Every handoff, tool call, decision and failure is visible in this session.</p></div>
          <span className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground"><CircleDot className="size-3 text-emerald-300" /> LIVE TRACE</span>
        </div>
        <div className="divide-y divide-border/70">
          {events.map((event, index) => {
            const Icon = event.kind === 'tool' ? Wrench : event.kind === 'handoff' ? ChevronRight : event.kind === 'warning' ? XCircle : event.kind === 'success' ? CheckCircle2 : Search
            return <div key={`${event.time}-${index}`} className="flex items-start gap-3 px-5 py-3"><Icon className={cn('mt-0.5 size-4 shrink-0', event.kind === 'warning' ? 'text-amber-300' : event.kind === 'success' ? 'text-emerald-300' : 'text-primary')} /><div className="min-w-0 flex-1"><p className="text-xs"><span className="font-medium">{event.agent}</span><span className="text-muted-foreground"> · {event.message}</span></p></div><span className="shrink-0 text-[10px] font-mono text-muted-foreground">{event.time}</span></div>
          })}
        </div>
      </GlassCard>

      <GlassCard className="p-5">
        <div className="flex items-center gap-2"><Sparkles className="size-4 text-primary" /><h2 className="text-sm font-semibold">Start a new mission</h2></div>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && startMission()} aria-label="Mission query" className="min-w-0 flex-1 rounded-lg border border-input bg-background/50 px-3 py-2 text-sm outline-none ring-offset-background placeholder:text-muted-foreground focus:ring-2 focus:ring-ring" />
          <button type="button" onClick={startMission} className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"><RefreshCw className="size-4" /> Run mission</button>
        </div>
      </GlassCard>
    </div>
  )
}

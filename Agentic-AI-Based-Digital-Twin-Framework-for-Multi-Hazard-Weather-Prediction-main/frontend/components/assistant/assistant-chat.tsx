'use client'

import { useRef, useState } from 'react'
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Send,
  Sparkles,
  User,
  Zap,
} from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { ASSISTANT_CANNED } from '@/lib/mock/extended-data'
import { askAssistant } from '@/lib/api/assistant'
import { queryOrchestrator, type OrchestratorResponse, type ToolCallRecord } from '@/lib/api/orchestrator'
import type { ChatMessage } from '@/types'
import { cn } from '@/lib/utils'

const RAG_SUGGESTIONS = [
  'What is the current flood risk for Mandi district?',
  'Explain the cloudburst probability for Kullu right now.',
  'What does the latest government flood advisory say for Mandi?',
  'Which infrastructure assets are at highest risk in the next 24 hours?',
  'Summarize recent disaster events in the Beas basin.',
]

// Extended message type that can carry orchestrator metadata
interface ExtendedMessage extends ChatMessage {
  toolsUsed?: ToolCallRecord[]
  intent?: OrchestratorResponse['intent']
  source?: 'orchestrator' | 'rag' | 'fallback'
}

function pickFallback(query: string): string {
  const q = query.toLowerCase()
  if (q.includes('flood') || q.includes('mandi')) return ASSISTANT_CANNED.flood
  if (q.includes('model') || q.includes('lstm') || q.includes('xgboost')) return ASSISTANT_CANNED.model
  return ASSISTANT_CANNED.default
}

function formatAssistantMessage(answer: string, sources: string[] | undefined): string {
  if (!sources || sources.length === 0) return answer
  return `${answer}\n\nSources:\n${sources.map((s) => `- ${s}`).join('\n')}`
}

function ToolBadge({ tool, success, duration_ms }: ToolCallRecord) {
  const label = tool.replace('_tool', '').replace('_', ' ')
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium',
        success
          ? 'border-primary/25 bg-primary/10 text-primary'
          : 'border-destructive/25 bg-destructive/10 text-destructive',
      )}
    >
      {success ? <CheckCircle2 className="size-2.5" /> : <Activity className="size-2.5" />}
      {label}
      <span className="opacity-60 font-mono">{duration_ms}ms</span>
    </span>
  )
}

function ToolPanel({ tools, intent }: { tools: ToolCallRecord[]; intent?: OrchestratorResponse['intent'] }) {
  const [open, setOpen] = useState(false)
  if (!tools.length) return null
  return (
    <div className="mt-2 rounded-lg border border-border/60 bg-background/40 text-[11px]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-3 py-1.5 text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Zap className="size-3 text-primary" />
          {tools.length} agent{tools.length > 1 ? 's' : ''} called
          {intent && (
            <span className="rounded bg-secondary/80 px-1.5 py-0.5 font-mono text-[10px]">
              {intent.intent_type} · {Math.round(intent.confidence * 100)}% conf
            </span>
          )}
        </span>
        {open ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
      </button>
      {open && (
        <div className="border-t border-border/40 px-3 py-2 flex flex-col gap-1.5">
          {tools.map((t) => (
            <div key={t.tool} className="flex items-start gap-2">
              <ToolBadge {...t} />
              <span className="text-muted-foreground text-pretty">{t.result_summary}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function AssistantChat() {
  const [messages, setMessages] = useState<ExtendedMessage[]>([
    {
      id: 'm-0',
      role: 'assistant',
      content:
        "I'm the multi-agent AI assistant for VARUNA. I coordinate the Weather, Prediction, Alert, and Digital Twin agents to answer questions about live hazard conditions. Ask anything — I'll route your query to the right specialist agents and synthesise a comprehensive response.",
      source: 'orchestrator',
    },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [thinkingLabel, setThinkingLabel] = useState('Thinking...')
  const listRef = useRef<HTMLDivElement>(null)

  async function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || thinking) return

    const userMsg: ExtendedMessage = { id: `m-${Date.now()}`, role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setThinking(true)
    setThinkingLabel('Routing to agents...')

    try {
      // Strategy 1: Full Orchestrator Agent (Weather + Prediction + Alert + Digital Twin + RAG)
      const result = await queryOrchestrator({ query: trimmed, session_id: 'assistant-ui' })
      const assistantMsg: ExtendedMessage = {
        id: `m-${Date.now()}-a`,
        role: 'assistant',
        content: result.response,
        toolsUsed: result.tools_used,
        intent: result.intent,
        source: 'orchestrator',
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch {
      // Strategy 2: RAG-only assistant fallback
      setThinkingLabel('Querying knowledge base...')
      try {
        const ragResult = await askAssistant(trimmed)
        setMessages((prev) => [
          ...prev,
          {
            id: `m-${Date.now()}-a`,
            role: 'assistant',
            content: formatAssistantMessage(ragResult.answer, ragResult.sources),
            source: 'rag',
          },
        ])
      } catch {
        // Strategy 3: Offline canned fallback
        setMessages((prev) => [
          ...prev,
          {
            id: `m-${Date.now()}-a`,
            role: 'assistant',
            content: `${pickFallback(trimmed)}\n\n_(Offline fallback — backend unreachable)_`,
            source: 'fallback',
          },
        ])
      }
    } finally {
      setThinking(false)
      setThinkingLabel('Thinking...')
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
      })
    }
  }

  return (
    <div className="grid lg:grid-cols-[1fr_280px] gap-6 flex-1 min-h-0">
      <GlassCard className="flex flex-col min-h-[60vh]">
        <div
          ref={listRef}
          className="flex-1 overflow-y-auto p-4 flex flex-col gap-4"
          aria-live="polite"
        >
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn('flex gap-3', m.role === 'user' ? 'flex-row-reverse' : '')}
            >
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-lg border',
                  m.role === 'assistant'
                    ? 'bg-primary/15 border-primary/25 text-primary'
                    : 'bg-secondary border-border text-muted-foreground',
                )}
              >
                {m.role === 'assistant' ? <Bot className="size-4" /> : <User className="size-4" />}
              </span>
              <div className="flex flex-col gap-1 max-w-[85%]">
                <div
                  className={cn(
                    'rounded-xl px-4 py-3 text-sm leading-relaxed text-pretty whitespace-pre-wrap',
                    m.role === 'assistant'
                      ? 'bg-secondary/60 border border-border'
                      : 'bg-primary/15 border border-primary/25',
                  )}
                >
                  {m.content}
                </div>
                {/* Tool call transparency panel for orchestrator messages */}
                {m.role === 'assistant' && m.toolsUsed && (
                  <ToolPanel tools={m.toolsUsed} intent={m.intent} />
                )}
                {/* Source badge */}
                {m.role === 'assistant' && m.source && m.source !== 'orchestrator' && (
                  <span className="flex items-center gap-1 text-[10px] text-muted-foreground pl-1">
                    <Clock className="size-2.5" />
                    {m.source === 'rag' ? 'RAG knowledge base' : 'Offline fallback'}
                  </span>
                )}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="flex gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 border border-primary/25 text-primary">
                <Bot className="size-4" />
              </span>
              <div className="rounded-xl px-4 py-3 bg-secondary/60 border border-border">
                <div className="flex items-center gap-2">
                  <span className="flex gap-1">
                    <span className="size-1.5 rounded-full bg-primary animate-bounce [animation-delay:0ms]" />
                    <span className="size-1.5 rounded-full bg-primary animate-bounce [animation-delay:150ms]" />
                    <span className="size-1.5 rounded-full bg-primary animate-bounce [animation-delay:300ms]" />
                  </span>
                  <span className="text-xs text-muted-foreground">{thinkingLabel}</span>
                </div>
              </div>
            </div>
          )}
        </div>
        <form
          className="border-t border-border p-3 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            send(input)
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about live hazards, risk forecasts, infrastructure, or project knowledge..."
            className="flex-1 bg-secondary/60 border border-border rounded-lg px-3 h-10 text-sm outline-none placeholder:text-muted-foreground focus:border-primary/40"
            aria-label="Message the assistant"
          />
          <button
            type="submit"
            disabled={!input.trim() || thinking}
            className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground disabled:opacity-40"
            aria-label="Send message"
          >
            <Send className="size-4" />
          </button>
        </form>
      </GlassCard>

      <div className="flex flex-col gap-3">
        <GlassCard className="p-4">
          <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            <Sparkles className="size-3.5 text-primary" aria-hidden="true" />
            Suggested Queries
          </h2>
          <p className="text-xs text-muted-foreground mb-3">
            Multi-agent queries — routed to Weather, Prediction, Alert &amp; Digital Twin agents automatically.
          </p>
          <ul className="flex flex-col gap-2">
            {RAG_SUGGESTIONS.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => send(s)}
                  className="w-full text-left text-xs rounded-lg border border-border bg-secondary/40 px-3 py-2 hover:border-primary/30 hover:text-primary transition-colors text-pretty"
                >
                  {s}
                </button>
              </li>
            ))}
          </ul>
        </GlassCard>
        <GlassCard className="p-4">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Agent Pipeline
          </h2>
          <ul className="flex flex-col gap-1.5 text-xs text-muted-foreground">
            <li className="flex justify-between"><span>Orchestrator</span><span className="text-green-400 font-mono">:8005</span></li>
            <li className="flex justify-between"><span>Weather Agent</span><span className="font-mono">:8001</span></li>
            <li className="flex justify-between"><span>Prediction Agent</span><span className="font-mono">:8002</span></li>
            <li className="flex justify-between"><span>Alert Agent</span><span className="font-mono">:8003</span></li>
            <li className="flex justify-between"><span>Digital Twin Agent</span><span className="font-mono">:8004</span></li>
            <li className="flex justify-between"><span>Report Agent</span><span className="font-mono">:8006</span></li>
          </ul>
        </GlassCard>
      </div>
    </div>
  )
}

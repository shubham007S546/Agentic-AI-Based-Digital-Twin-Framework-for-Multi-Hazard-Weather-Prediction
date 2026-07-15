'use client'

import { useRef, useState } from 'react'
import { Bot, Send, Sparkles, User } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { ASSISTANT_SUGGESTIONS, ASSISTANT_CANNED } from '@/lib/mock/extended-data'
import type { ChatMessage } from '@/types'
import { cn } from '@/lib/utils'

function pickResponse(query: string): string {
  const q = query.toLowerCase()
  if (q.includes('flood') || q.includes('mandi')) return ASSISTANT_CANNED.flood
  if (q.includes('model') || q.includes('lstm') || q.includes('xgboost') || q.includes('compare'))
    return ASSISTANT_CANNED.model
  return ASSISTANT_CANNED.default
}

export function AssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm-0',
      role: 'assistant',
      content:
        "I'm the Shubham intelligence agent. I can reason over live weather, hazard predictions, river gauges, terrain layers and model diagnostics. Ask me anything about the current situation.",
    },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || thinking) return
    const userMsg: ChatMessage = { id: `m-${Date.now()}`, role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setThinking(true)
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: `m-${Date.now()}-a`, role: 'assistant', content: pickResponse(trimmed) },
      ])
      setThinking(false)
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
      })
    }, 900)
    requestAnimationFrame(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
    })
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
              <div
                className={cn(
                  'rounded-xl px-4 py-3 text-sm leading-relaxed max-w-[85%] text-pretty',
                  m.role === 'assistant'
                    ? 'bg-secondary/60 border border-border'
                    : 'bg-primary/15 border border-primary/25',
                )}
              >
                {m.content}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="flex gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 border border-primary/25 text-primary">
                <Bot className="size-4" />
              </span>
              <div className="rounded-xl px-4 py-3 bg-secondary/60 border border-border">
                <span className="flex gap-1">
                  <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                  <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                  <span className="size-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
                </span>
                <span className="sr-only">Assistant is thinking</span>
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
            placeholder="Ask about hazards, models, districts, assets..."
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
          <ul className="flex flex-col gap-2">
            {ASSISTANT_SUGGESTIONS.map((s) => (
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
            Agent Context
          </h2>
          <ul className="flex flex-col gap-1.5 text-xs text-muted-foreground">
            <li className="flex justify-between"><span>Model run</span><span className="font-mono">06:00 IST</span></li>
            <li className="flex justify-between"><span>Live gauges</span><span className="font-mono">50</span></li>
            <li className="flex justify-between"><span>Active alerts</span><span className="font-mono text-destructive">4</span></li>
            <li className="flex justify-between"><span>Data sources</span><span className="font-mono">14</span></li>
            <li className="flex justify-between"><span>Tools available</span><span className="font-mono">8</span></li>
          </ul>
        </GlassCard>
      </div>
    </div>
  )
}

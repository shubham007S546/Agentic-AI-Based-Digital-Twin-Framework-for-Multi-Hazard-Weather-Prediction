'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

type AuthTab = 'signin' | 'signup'

export function AuthForm() {
  const router = useRouter()
  const [tab, setTab] = useState<AuthTab>('signin')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!email.trim() || !password.trim() || (tab === 'signup' && !name.trim())) {
      setError('Please fill in all required fields.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    // Demo environment: simulate authentication then enter the platform.
    setTimeout(() => {
      router.push('/dashboard')
    }, 900)
  }

  return (
    <div className="glass-strong rounded-xl p-6 w-full shadow-xl shadow-black/40">
      <div className="flex gap-1 rounded-lg bg-secondary/60 p-1 mb-5" role="tablist" aria-label="Authentication">
        {(
          [
            { id: 'signin', label: 'Sign In' },
            { id: 'signup', label: 'Request Access' },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => {
              setTab(t.id)
              setError(null)
            }}
            className={cn(
              'flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors',
              tab === t.id
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {tab === 'signup' && (
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium">Full name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              placeholder="Dr. Rajat Sharma"
              className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
            />
          </label>
        )}

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium">Institutional email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            placeholder="name@iitmandi.ac.in"
            className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-medium">Password</span>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={tab === 'signin' ? 'current-password' : 'new-password'}
              placeholder="At least 8 characters"
              className="w-full rounded-lg bg-secondary border border-border px-3 py-2.5 pr-10 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </label>

        {tab === 'signin' && (
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" defaultChecked className="accent-[var(--primary)]" />
              Remember me
            </label>
            <button type="button" className="text-xs text-primary hover:underline">
              Forgot password?
            </button>
          </div>
        )}

        {error && (
          <p role="alert" className="rounded-lg bg-destructive/10 border border-destructive/25 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="mt-1 inline-flex items-center justify-center gap-2 rounded-lg bg-primary text-primary-foreground px-4 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
        >
          {loading && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
          {tab === 'signin' ? 'Sign In to VARUNA' : 'Submit Access Request'}
        </button>

        <p className="text-[11px] text-muted-foreground text-center text-pretty">
          {tab === 'signin'
            ? 'Access is limited to authorised researchers and disaster management officials.'
            : 'Requests are reviewed by the platform administrator within one working day.'}
        </p>
      </form>
    </div>
  )
}

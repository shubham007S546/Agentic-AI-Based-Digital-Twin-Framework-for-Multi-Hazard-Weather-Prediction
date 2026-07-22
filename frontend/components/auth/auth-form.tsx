'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Loader2, CheckCircle2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/use-auth'
import { requestAccess } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'

type AuthTab = 'signin' | 'signup'

export function AuthForm() {
  const router = useRouter()
  const { login } = useAuth()
  const [tab, setTab] = useState<AuthTab>('signin')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  // Login form state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // Request Access form state
  const [fullName, setFullName] = useState('')
  const [signupEmail, setSignupEmail] = useState('')
  const [institution, setInstitution] = useState('')
  const [department, setDepartment] = useState('')
  const [purpose, setPurpose] = useState('')
  const [researchArea, setResearchArea] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccessMsg(null)
    setLoading(true)

    try {
      if (tab === 'signin') {
        if (!email.trim() || !password.trim()) {
          setError('Please fill in all required fields.')
          setLoading(false)
          return
        }
        await login({ email, password })
        router.push('/dashboard')
      } else {
        if (
          !fullName.trim() ||
          !signupEmail.trim() ||
          !institution.trim() ||
          !department.trim() ||
          !purpose.trim()
        ) {
          setError('Please fill in all required fields.')
          setLoading(false)
          return
        }
        await requestAccess({
          full_name: fullName,
          email: signupEmail,
          institution,
          department,
          purpose,
          research_area: researchArea || undefined,
        })
        setSuccessMsg('Your access request has been submitted successfully! The administrator will review your application.')
        // Clear request access form fields
        setFullName('')
        setSignupEmail('')
        setInstitution('')
        setDepartment('')
        setPurpose('')
        setResearchArea('')
      }
    } catch (err: any) {
      if (err instanceof ApiError) {
        // Look for structured error format or fall back to status code messages
        try {
          const parsed = JSON.parse(err.message)
          setError(parsed?.error?.message || parsed?.message || 'Authentication error.')
        } catch {
          if (err.status === 401) {
            setError('Invalid email or password.')
          } else if (err.status === 403) {
            setError('Your account is inactive or locked.')
          } else {
            setError(err.message || 'An unexpected error occurred.')
          }
        }
      } else {
        setError('Connection failed. Please ensure the backend server is running.')
      }
    } finally {
      setLoading(false)
    }
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
              setSuccessMsg(null)
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

      {successMsg ? (
        <div className="flex flex-col items-center text-center py-6 gap-3">
          <CheckCircle2 className="size-12 text-emerald-500 animate-pulse" />
          <h3 className="text-sm font-semibold text-foreground">Request Submitted</h3>
          <p className="text-xs text-muted-foreground px-4 leading-relaxed">
            {successMsg}
          </p>
          <button
            onClick={() => {
              setTab('signin')
              setSuccessMsg(null)
            }}
            className="mt-4 text-xs font-medium text-primary hover:underline"
          >
            Back to Sign In
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {tab === 'signin' ? (
            <>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Email address</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="name@iitmandi.ac.in"
                  className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                  required
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Password</span>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    placeholder="Enter password"
                    className="w-full rounded-lg bg-secondary border border-border px-3 py-2.5 pr-10 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                    required
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

              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input type="checkbox" defaultChecked className="accent-[var(--primary)]" />
                  Remember me
                </label>
                <button type="button" className="text-xs text-primary hover:underline">
                  Forgot password?
                </button>
              </div>
            </>
          ) : (
            <>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Full name</span>
                <input
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Full Name"
                  className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                  required
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Institutional email</span>
                <input
                  type="email"
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                  placeholder="name@iitmandi.ac.in"
                  className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                  required
                />
              </label>

              <div className="grid grid-cols-2 gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Institution/Org</span>
                  <input
                    value={institution}
                    onChange={(e) => setInstitution(e.target.value)}
                    placeholder="IIT Mandi"
                    className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                    required
                  />
                </label>

                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Department</span>
                  <input
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="SCEE"
                    className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                    required
                  />
                </label>
              </div>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Research Area (Optional)</span>
                <input
                  value={researchArea}
                  onChange={(e) => setResearchArea(e.target.value)}
                  placeholder="Hydro-meteorological modeling"
                  className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                />
              </label>

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium">Purpose of Access</span>
                <textarea
                  value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}
                  placeholder="Explain how you will use the prediction platform..."
                  className="rounded-lg bg-secondary border border-border px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground resize-none h-20"
                  required
                />
              </label>
            </>
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
      )}
    </div>
  )
}


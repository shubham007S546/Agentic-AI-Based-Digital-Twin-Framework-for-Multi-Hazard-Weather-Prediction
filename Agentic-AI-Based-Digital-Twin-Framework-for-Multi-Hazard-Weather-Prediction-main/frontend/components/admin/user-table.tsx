'use client'

import { useMemo, useState } from 'react'
import { Search, UserPlus, X } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { PLATFORM_USERS, type PlatformUser } from '@/lib/mock/extended-data'
import { cn } from '@/lib/utils'

const STATUS_STYLES: Record<PlatformUser['status'], string> = {
  active: 'bg-success/15 text-success border-success/30',
  invited: 'bg-primary/15 text-primary border-primary/30',
  suspended: 'bg-destructive/15 text-destructive border-destructive/30',
}

const ROLE_STYLES: Record<PlatformUser['role'], string> = {
  Admin: 'bg-primary/15 text-primary border-primary/30',
  Researcher: 'bg-secondary text-foreground border-border',
  Analyst: 'bg-secondary text-foreground border-border',
  'District Officer': 'bg-secondary text-foreground border-border',
  Viewer: 'bg-secondary text-muted-foreground border-border',
}

const ROLES = ['All', 'Admin', 'Researcher', 'Analyst', 'District Officer', 'Viewer'] as const

function initials(name: string) {
  return name
    .replace(/^Dr\.\s+/, '')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

export function UserTable() {
  const [query, setQuery] = useState('')
  const [role, setRole] = useState<(typeof ROLES)[number]>('All')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteSent, setInviteSent] = useState(false)

  const filtered = useMemo(
    () =>
      PLATFORM_USERS.filter(
        (u) =>
          (role === 'All' || u.role === role) &&
          (u.name.toLowerCase().includes(query.toLowerCase()) ||
            u.email.toLowerCase().includes(query.toLowerCase()) ||
            u.org.toLowerCase().includes(query.toLowerCase())),
      ),
    [query, role],
  )

  function handleInvite(e: React.FormEvent) {
    e.preventDefault()
    if (!inviteEmail.trim()) return
    setInviteSent(true)
    setTimeout(() => {
      setInviteOpen(false)
      setInviteSent(false)
      setInviteEmail('')
    }, 1400)
  }

  return (
    <GlassCard className="p-0 overflow-hidden">
      <div className="p-5 pb-3 flex flex-col sm:flex-row sm:items-center gap-3">
        <h2 className="text-sm font-medium shrink-0">Users &amp; Roles</h2>
        <div className="relative flex-1 max-w-sm sm:ml-2">
          <Search
            className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name, email or organisation..."
            aria-label="Search users"
            className="w-full rounded-lg bg-secondary border border-border pl-9 pr-3 py-2 text-xs outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {ROLES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRole(r)}
              aria-pressed={role === r}
              className={cn(
                'px-2.5 py-1 rounded-full border text-[11px] font-medium transition-colors',
                role === r
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
              )}
            >
              {r}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setInviteOpen(true)}
          className="sm:ml-auto inline-flex items-center gap-1.5 rounded-lg bg-primary text-primary-foreground px-3 py-2 text-xs font-medium hover:opacity-90 transition-opacity"
        >
          <UserPlus className="size-3.5" aria-hidden="true" />
          Invite User
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-y border-border text-muted-foreground">
              <th className="text-left font-medium px-5 py-2.5" scope="col">
                User
              </th>
              <th className="text-left font-medium px-3 py-2.5" scope="col">
                Role
              </th>
              <th className="text-left font-medium px-3 py-2.5" scope="col">
                Organisation
              </th>
              <th className="text-left font-medium px-3 py-2.5" scope="col">
                Last Active
              </th>
              <th className="text-left font-medium px-5 py-2.5" scope="col">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr
                key={u.id}
                className="border-b border-border/50 hover:bg-secondary/40 transition-colors"
              >
                <td className="px-5 py-2.5">
                  <div className="flex items-center gap-3">
                    <span
                      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/15 border border-primary/25 text-primary text-[10px] font-semibold"
                      aria-hidden="true"
                    >
                      {initials(u.name)}
                    </span>
                    <div className="min-w-0">
                      <p className="font-medium whitespace-nowrap">{u.name}</p>
                      <p className="text-muted-foreground font-mono text-[10px] truncate">
                        {u.email}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium whitespace-nowrap',
                      ROLE_STYLES[u.role],
                    )}
                  >
                    {u.role}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-muted-foreground whitespace-nowrap">{u.org}</td>
                <td className="px-3 py-2.5 font-mono tabular-nums text-muted-foreground whitespace-nowrap">
                  {u.lastActive}
                </td>
                <td className="px-5 py-2.5">
                  <span
                    className={cn(
                      'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize',
                      STATUS_STYLES[u.status],
                    )}
                  >
                    {u.status}
                  </span>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-muted-foreground">
                  No users match your filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {inviteOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="invite-user-title"
        >
          <button
            type="button"
            aria-label="Close dialog"
            className="absolute inset-0 bg-black/60"
            onClick={() => setInviteOpen(false)}
          />
          <div className="relative glass-strong rounded-xl p-5 w-full max-w-sm shadow-xl shadow-black/40">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 id="invite-user-title" className="text-sm font-medium">
                  Invite User
                </h3>
                <p className="text-xs text-muted-foreground mt-1">
                  Send an invitation to join the VARUNA platform.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setInviteOpen(false)}
                aria-label="Close"
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            {inviteSent ? (
              <p className="mt-4 rounded-lg bg-success/10 border border-success/25 px-3 py-2.5 text-xs text-success">
                Invitation sent to {inviteEmail}.
              </p>
            ) : (
              <form onSubmit={handleInvite} className="mt-4 flex flex-col gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Email address</span>
                  <input
                    type="email"
                    required
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="name@organisation.gov.in"
                    className="rounded-lg bg-secondary border border-border px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-primary/40 placeholder:text-muted-foreground"
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium">Role</span>
                  <select
                    defaultValue="Viewer"
                    className="rounded-lg bg-secondary border border-border px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-primary/40"
                  >
                    {ROLES.filter((r) => r !== 'All').map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                </label>
                <button
                  type="submit"
                  className="mt-1 rounded-lg bg-primary text-primary-foreground px-3 py-2 text-xs font-medium hover:opacity-90 transition-opacity"
                >
                  Send Invitation
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </GlassCard>
  )
}

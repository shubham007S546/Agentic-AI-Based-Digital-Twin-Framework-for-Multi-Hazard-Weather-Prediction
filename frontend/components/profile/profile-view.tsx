'use client'

import { useState, useEffect } from 'react'
import { BadgeCheck, Building2, Mail, MapPin, ShieldCheck, Smartphone } from 'lucide-react'
import { GlassCard } from '@/components/shared/glass-card'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/use-auth'

const RECENT_ACTIVITY = [
  { time: '07:12 IST', action: 'Approved alert AL-1 for public dispatch' },
  { time: '06:45 IST', action: 'Reviewed cloudburst watch for Kullu district' },
  { time: 'Yesterday', action: 'Generated monsoon situation report (PDF)' },
  { time: 'Yesterday', action: 'Invited rohit.c@hpsdma.nic.in as Viewer' },
  { time: '12 Jul', action: 'Updated flood threshold for Pandoh gauge' },
  { time: '11 Jul', action: 'Exported master dataset v14 metadata' },
]

const DISTRICT_SUBSCRIPTIONS = ['Mandi', 'Kullu', 'Kangra', 'Shimla', 'Chamba']

export function ProfileView() {
  const { user } = useAuth()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(user?.full_name || 'User')
  const [phone, setPhone] = useState('+91 98160 00000')
  const [districts, setDistricts] = useState<string[]>(['Mandi', 'Kullu', 'Kangra'])
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (user) {
      setName(user.full_name)
    }
  }, [user])

  function toggleDistrict(d: string) {
    setDistricts((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))
  }

  function save() {
    setEditing(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 1800)
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <GlassCard className="p-5 xl:col-span-1">
        <div className="flex items-center gap-4">
          <span
            className="flex size-14 shrink-0 items-center justify-center rounded-full bg-primary/15 border border-primary/25 text-primary text-lg font-semibold"
            aria-hidden="true"
          >
            {name ? name.split(' ').map((x) => x[0]).join('').toUpperCase().slice(0, 2) : 'U'}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <h2 className="text-sm font-semibold truncate">{name}</h2>
              <BadgeCheck className="size-4 text-primary shrink-0" aria-label="Verified" />
            </div>
            <span className="inline-flex items-center gap-1 mt-1 rounded-full bg-primary/15 border border-primary/30 px-2 py-0.5 text-[10px] font-medium text-primary">
              <ShieldCheck className="size-3" aria-hidden="true" />
              {user ? user.role : 'Member'}
            </span>
          </div>
        </div>

        <dl className="mt-5 flex flex-col gap-3 text-xs">
          <div className="flex items-center gap-2.5">
            <Mail className="size-4 text-muted-foreground shrink-0" aria-hidden="true" />
            <dt className="sr-only">Email</dt>
            <dd className="font-mono truncate">{user ? user.email : 'user@example.com'}</dd>
          </div>
          <div className="flex items-center gap-2.5">
            <Smartphone className="size-4 text-muted-foreground shrink-0" aria-hidden="true" />
            <dt className="sr-only">Phone</dt>
            <dd className="font-mono">
              {editing ? (
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  aria-label="Phone number"
                  className="rounded-lg bg-secondary border border-border px-2 py-1 text-xs font-mono outline-none focus:ring-2 focus:ring-primary/40"
                />
              ) : (
                phone
              )}
            </dd>
          </div>
          <div className="flex items-center gap-2.5">
            <Building2 className="size-4 text-muted-foreground shrink-0" aria-hidden="true" />
            <dt className="sr-only">Organisation</dt>
            <dd>
              {user?.organization
                ? `${user.organization}${user.department ? ` · ${user.department}` : ''}`
                : 'IIT Mandi · Centre for AI & Disaster Research'}
            </dd>
          </div>
          <div className="flex items-center gap-2.5">
            <MapPin className="size-4 text-muted-foreground shrink-0" aria-hidden="true" />
            <dt className="sr-only">Location</dt>
            <dd>Kamand, Himachal Pradesh</dd>
          </div>
        </dl>

        {editing && (
          <div className="mt-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium">Display name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="rounded-lg bg-secondary border border-border px-3 py-2 text-xs outline-none focus:ring-2 focus:ring-primary/40"
              />
            </label>
          </div>
        )}

        <div className="mt-5 pt-4 border-t border-border/50 flex items-center gap-2">
          {editing ? (
            <>
              <button
                type="button"
                onClick={save}
                className="rounded-lg bg-primary text-primary-foreground px-3 py-2 text-xs font-medium hover:opacity-90 transition-opacity"
              >
                Save Profile
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-lg bg-secondary border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg bg-secondary border border-border px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Edit Profile
            </button>
          )}
          {saved && <span className="text-[11px] text-success">Profile updated.</span>}
        </div>
      </GlassCard>

      <GlassCard className="p-5 xl:col-span-1">
        <h2 className="text-sm font-medium mb-1">District Subscriptions</h2>
        <p className="text-xs text-muted-foreground mb-4">
          You receive alerts and digests for the districts selected below.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {DISTRICT_SUBSCRIPTIONS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => toggleDistrict(d)}
              aria-pressed={districts.includes(d)}
              className={cn(
                'px-3 py-1.5 rounded-full border text-xs font-medium transition-colors',
                districts.includes(d)
                  ? 'bg-primary/15 text-primary border-primary/30'
                  : 'bg-secondary text-muted-foreground border-border hover:text-foreground',
              )}
            >
              {d}
            </button>
          ))}
        </div>

        <div className="mt-6 pt-4 border-t border-border/50">
          <h3 className="text-xs font-medium mb-3 text-muted-foreground uppercase tracking-wider">
            Security
          </h3>
          <ul className="flex flex-col gap-3 text-xs">
            <li className="flex items-center justify-between gap-3">
              <span>Two-factor authentication</span>
              <span className="inline-flex items-center rounded-full bg-success/15 text-success border border-success/30 px-2 py-0.5 text-[10px] font-medium">
                Enabled
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span>Password last changed</span>
              <span className="font-mono text-muted-foreground">04 May 2026</span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span>Active sessions</span>
              <span className="font-mono text-muted-foreground">2 devices</span>
            </li>
          </ul>
        </div>
      </GlassCard>

      <GlassCard className="p-5 xl:col-span-1">
        <h2 className="text-sm font-medium mb-4">Recent Activity</h2>
        <ol className="flex flex-col">
          {RECENT_ACTIVITY.map((entry, i) => (
            <li key={`${entry.time}-${i}`} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span className="size-2 rounded-full bg-primary/60 shrink-0 mt-1.5" aria-hidden="true" />
                {i < RECENT_ACTIVITY.length - 1 && <span className="w-px flex-1 bg-border my-1" />}
              </div>
              <div className="pb-4 min-w-0">
                <p className="text-xs text-pretty">{entry.action}</p>
                <span className="text-[10px] text-muted-foreground font-mono">{entry.time}</span>
              </div>
            </li>
          ))}
        </ol>
      </GlassCard>
    </div>
  )
}

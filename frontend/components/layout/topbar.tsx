'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Bell, Menu, Search, X, Radar } from 'lucide-react'
import { NAV_SECTIONS, PLATFORM_NAME } from '@/lib/constants/navigation'
import { ALERTS } from '@/lib/mock/data'
import { RiskBadge } from '@/components/shared/risk-badge'
import { useAuth } from '@/hooks/use-auth'
import { cn } from '@/lib/utils'

export function Topbar() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const pathname = usePathname()
  const { user } = useAuth()
  const current = NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.href === pathname)

  const getInitials = (name?: string) => {
    if (!name) return 'U'
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }

  const initials = user ? getInitials(user.full_name) : 'U'

  return (
    <header className="sticky top-0 z-40 glass-strong border-b border-border h-14 flex items-center gap-3 px-4">
      <button
        type="button"
        className="md:hidden text-muted-foreground hover:text-foreground"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      <div className="flex items-center gap-2 min-w-0">
        <h2 className="text-sm font-medium truncate">{current?.label ?? 'Platform'}</h2>
        <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-success/10 border border-success/25 px-2 py-0.5 text-[10px] text-success">
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex size-full rounded-full bg-success opacity-60 animate-ping" />
            <span className="relative inline-flex size-1.5 rounded-full bg-success" />
          </span>
          LIVE
        </span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <div className="hidden lg:flex items-center gap-2 rounded-lg bg-secondary/60 border border-border px-3 h-9 w-64">
          <Search className="size-3.5 text-muted-foreground" aria-hidden="true" />
          <input
            placeholder="Search stations, districts, layers..."
            className="bg-transparent text-sm outline-none w-full placeholder:text-muted-foreground"
            aria-label="Search"
          />
        </div>

        <div className="relative">
          <button
            type="button"
            onClick={() => setAlertsOpen((v) => !v)}
            className="relative flex size-9 items-center justify-center rounded-lg border border-border bg-secondary/60 text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Alerts"
          >
            <Bell className="size-4" />
            <span className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-white">
              {ALERTS.length}
            </span>
          </button>
          {alertsOpen && (
            <div className="absolute right-0 mt-2 w-80 glass-strong rounded-xl p-2 shadow-xl shadow-black/40">
              <p className="px-2 py-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Active Alerts
              </p>
              <ul className="flex flex-col gap-1 max-h-80 overflow-y-auto">
                {ALERTS.map((a) => (
                  <li key={a.id} className="rounded-lg p-2 hover:bg-secondary/60">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{a.title}</span>
                      <RiskBadge risk={a.severity} />
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{a.message}</p>
                    <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                      {a.district}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <Link
          href="/profile"
          className="flex size-9 items-center justify-center rounded-lg bg-primary/15 border border-primary/25 text-primary text-xs font-semibold"
          aria-label="Account"
        >
          {initials}
        </Link>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 bg-sidebar border-r border-sidebar-border overflow-y-auto">
            <div className="flex items-center justify-between px-4 h-14 border-b border-sidebar-border">
              <span className="flex items-center gap-2 text-sm font-semibold">
                <Radar className="size-4 text-primary" aria-hidden="true" />
                {PLATFORM_NAME}
              </span>
              <button type="button" onClick={() => setMobileOpen(false)} aria-label="Close">
                <X className="size-5 text-muted-foreground" />
              </button>
            </div>
            <nav className="p-3 flex flex-col gap-4" aria-label="Mobile">
              {NAV_SECTIONS.map((section) => (
                <div key={section.title}>
                  <p className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    {section.title}
                  </p>
                  <ul>
                    {section.items.map((item) => (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          onClick={() => setMobileOpen(false)}
                          className={cn(
                            'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm',
                            pathname === item.href
                              ? 'bg-primary/15 text-primary'
                              : 'text-sidebar-foreground/75',
                          )}
                        >
                          <item.icon className="size-4" aria-hidden="true" />
                          {item.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </nav>
          </div>
        </div>
      )}
    </header>
  )
}

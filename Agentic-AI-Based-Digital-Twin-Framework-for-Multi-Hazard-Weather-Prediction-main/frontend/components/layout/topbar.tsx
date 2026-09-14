'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Bell, Menu, Search, X, Radar, ChevronRight } from 'lucide-react'
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
  const criticalCount = ALERTS.filter((a) => a.severity === 'extreme' || a.severity === 'high').length

  return (
    <header className="sticky top-0 z-40 glass-strong border-b border-border h-14 flex items-center gap-3 px-4">
      {/* Mobile hamburger */}
      <button
        type="button"
        className="md:hidden text-muted-foreground hover:text-foreground"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
      >
        <Menu className="size-5" />
      </button>

      {/* Page breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        <h2 className="text-sm font-semibold truncate text-foreground">{current?.label ?? 'Platform'}</h2>
        <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-success/10 border border-success/25 px-2 py-0.5 text-[10px] font-medium text-success">
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex size-full rounded-full bg-success opacity-60 animate-ping" />
            <span className="relative inline-flex size-1.5 rounded-full bg-success" />
          </span>
          LIVE
        </span>
      </div>

      {/* Right actions */}
      <div className="ml-auto flex items-center gap-2">
        {/* Search */}
        <div className="hidden lg:flex items-center gap-2 rounded-lg bg-secondary/60 border border-border px-3 h-9 w-64">
          <Search className="size-3.5 text-muted-foreground shrink-0" aria-hidden="true" />
          <input
            placeholder="Search districts, hazards, stations..."
            className="bg-transparent text-sm outline-none w-full placeholder:text-muted-foreground/60"
            aria-label="Search"
          />
          <kbd className="hidden xl:flex items-center gap-0.5 text-[9px] text-muted-foreground/50 font-mono border border-border rounded px-1">
            ⌘K
          </kbd>
        </div>

        {/* Alerts bell */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setAlertsOpen((v) => !v)}
            className="relative flex size-9 items-center justify-center rounded-lg border border-border bg-secondary/60 text-muted-foreground hover:text-foreground transition-colors"
            aria-label={`${ALERTS.length} active alerts`}
          >
            <Bell className="size-4" />
            {criticalCount > 0 && (
              <span className="absolute -top-1 -right-1 flex size-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-white leading-none">
                {criticalCount}
              </span>
            )}
          </button>

          {alertsOpen && (
            <>
              <button
                type="button"
                className="fixed inset-0 z-40"
                aria-label="Close alerts"
                onClick={() => setAlertsOpen(false)}
              />
              <div className="absolute right-0 mt-2 w-80 glass-strong rounded-xl overflow-hidden shadow-xl shadow-black/40 z-50">
                <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/60">
                  <p className="text-xs font-semibold text-foreground">Active Alerts</p>
                  <Link
                    href="/alerts"
                    onClick={() => setAlertsOpen(false)}
                    className="text-[10px] text-primary hover:underline flex items-center gap-0.5"
                  >
                    View all <ChevronRight className="size-3" />
                  </Link>
                </div>
                <ul className="flex flex-col max-h-80 overflow-y-auto divide-y divide-border/40">
                  {ALERTS.map((a) => (
                    <li key={a.id} className="px-3 py-2.5 hover:bg-secondary/40 transition-colors">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium leading-tight truncate">{a.title}</p>
                          <p className="text-[10px] text-muted-foreground mt-0.5 font-mono">{a.district}</p>
                        </div>
                        <RiskBadge risk={a.severity} />
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">{a.message}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>

        {/* User avatar */}
        <div
          className="flex size-9 items-center justify-center rounded-lg bg-primary/15 border border-primary/25 text-primary text-xs font-bold cursor-default select-none"
          aria-label="Account"
          title={user?.full_name ?? 'User'}
        >
          {initials}
        </div>
      </div>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 bg-sidebar border-r border-sidebar-border overflow-y-auto flex flex-col">
            <div className="flex items-center justify-between px-4 h-14 border-b border-sidebar-border shrink-0">
              <span className="flex items-center gap-2 text-sm font-bold">
                <Radar className="size-4 text-primary" aria-hidden="true" />
                {PLATFORM_NAME}
              </span>
              <button type="button" onClick={() => setMobileOpen(false)} aria-label="Close">
                <X className="size-5 text-muted-foreground" />
              </button>
            </div>
            <nav className="flex-1 p-3 flex flex-col gap-5 overflow-y-auto" aria-label="Mobile navigation">
              {NAV_SECTIONS.map((section) => (
                <div key={section.title}>
                  <p className="px-2 mb-1 text-[9px] font-bold uppercase tracking-[0.15em] text-muted-foreground/50">
                    {section.title}
                  </p>
                  <ul className="flex flex-col gap-px">
                    {section.items.map((item) => (
                      <li key={item.href}>
                        <Link
                          href={item.href}
                          onClick={() => setMobileOpen(false)}
                          className={cn(
                            'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium',
                            pathname === item.href
                              ? 'bg-primary/12 text-primary'
                              : 'text-sidebar-foreground/60 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground',
                          )}
                        >
                          <item.icon className="size-4 shrink-0" aria-hidden="true" />
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

'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Radar, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { NAV_SECTIONS, PLATFORM_NAME, PLATFORM_TAGLINE } from '@/lib/constants/navigation'
import { useAppStore } from '@/store/use-app-store'
import { cn } from '@/lib/utils'

export function Sidebar() {
  const pathname = usePathname()
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col shrink-0 border-r border-sidebar-border bg-sidebar transition-[width] duration-300 ease-in-out h-svh sticky top-0 z-30 overflow-hidden',
        collapsed ? 'w-[60px]' : 'w-[240px]',
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-3 h-14 border-b border-sidebar-border shrink-0">
        <div className="relative flex size-9 items-center justify-center rounded-xl bg-primary/15 border border-primary/20 shrink-0">
          <Radar className="size-4.5 text-primary" aria-hidden="true" />
          <span className="absolute -top-0.5 -right-0.5 size-2 rounded-full bg-success border-2 border-sidebar" />
        </div>
        {!collapsed && (
          <div className="min-w-0 flex-1">
            <p className="text-[13px] font-bold tracking-wider text-foreground">{PLATFORM_NAME}</p>
            <p className="text-[10px] text-muted-foreground/70 truncate font-medium tracking-wide uppercase">{PLATFORM_TAGLINE}</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden py-3 px-2 flex flex-col gap-5 scrollbar-none"
        aria-label="Primary navigation"
        style={{ scrollbarWidth: 'none' }}
      >
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="flex flex-col gap-0.5">
            {!collapsed && (
              <p className="px-2 mb-1 text-[9px] font-bold uppercase tracking-[0.15em] text-muted-foreground/50 select-none">
                {section.title}
              </p>
            )}
            {collapsed && <div className="mx-auto w-4 h-px bg-sidebar-border/60 mb-1" />}
            <ul className="flex flex-col gap-px">
              {section.items.map((item) => {
                const active = pathname === item.href
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        'group relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-all duration-150',
                        active
                          ? 'bg-primary/12 text-primary'
                          : 'text-sidebar-foreground/60 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground',
                        collapsed && 'justify-center px-0 w-10 mx-auto',
                      )}
                    >
                      {active && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-full bg-primary" />
                      )}
                      <item.icon
                        className={cn(
                          'size-[15px] shrink-0 transition-colors',
                          active ? 'text-primary' : 'text-sidebar-foreground/50 group-hover:text-sidebar-foreground',
                        )}
                        aria-hidden="true"
                      />
                      {!collapsed && (
                        <span className="truncate">{item.label}</span>
                      )}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* System Status */}
      {!collapsed && (
        <div className="mx-3 mb-3 rounded-lg border border-sidebar-border/60 bg-sidebar-accent/30 px-3 py-2.5">
          <p className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-widest mb-1.5">System Status</p>
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">AI Agents</span>
              <span className="flex items-center gap-1 text-[10px] text-success font-medium">
                <span className="size-1.5 rounded-full bg-success animate-pulse" />
                Active
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">Data Feeds</span>
              <span className="text-[10px] text-success font-medium">Online</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">Model Confidence</span>
              <span className="text-[10px] text-primary font-mono font-medium">87.4%</span>
            </div>
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        type="button"
        onClick={toggle}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className="flex items-center justify-center gap-2 h-10 border-t border-sidebar-border text-muted-foreground/50 hover:text-muted-foreground transition-colors text-xs shrink-0"
      >
        {collapsed ? (
          <PanelLeftOpen className="size-4" aria-hidden="true" />
        ) : (
          <>
            <PanelLeftClose className="size-4" aria-hidden="true" />
            <span className="text-[11px]">Collapse</span>
          </>
        )}
      </button>
    </aside>
  )
}

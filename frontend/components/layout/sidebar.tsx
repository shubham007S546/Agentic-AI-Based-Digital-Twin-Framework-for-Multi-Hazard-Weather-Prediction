'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Radar, ChevronsLeft, ChevronsRight } from 'lucide-react'
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
        'hidden md:flex flex-col shrink-0 border-r border-sidebar-border bg-sidebar transition-[width] duration-300 h-svh sticky top-0',
        collapsed ? 'w-16' : 'w-60',
      )}
    >
      <Link
        href="/"
        className="flex items-center gap-2.5 px-4 h-14 border-b border-sidebar-border shrink-0"
      >
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15 text-primary shrink-0">
          <Radar className="size-4.5" aria-hidden="true" />
        </span>
        {!collapsed && (
          <span className="min-w-0">
            <span className="block text-sm font-semibold tracking-wide">{PLATFORM_NAME}</span>
            <span className="block text-[10px] text-muted-foreground truncate">
              {PLATFORM_TAGLINE}
            </span>
          </span>
        )}
      </Link>

      <nav className="flex-1 overflow-y-auto py-3 px-2 flex flex-col gap-4" aria-label="Primary">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title}>
            {!collapsed && (
              <p className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {section.title}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {section.items.map((item) => {
                const active = pathname === item.href
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        'flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                        active
                          ? 'bg-primary/15 text-primary font-medium'
                          : 'text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-foreground',
                        collapsed && 'justify-center px-0',
                      )}
                    >
                      <item.icon className="size-4 shrink-0" aria-hidden="true" />
                      {!collapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <button
        type="button"
        onClick={toggle}
        className="flex items-center justify-center gap-2 h-11 border-t border-sidebar-border text-muted-foreground hover:text-foreground transition-colors text-xs"
      >
        {collapsed ? (
          <ChevronsRight className="size-4" aria-hidden="true" />
        ) : (
          <>
            <ChevronsLeft className="size-4" aria-hidden="true" />
            Collapse
          </>
        )}
        <span className="sr-only">Toggle sidebar</span>
      </button>
    </aside>
  )
}

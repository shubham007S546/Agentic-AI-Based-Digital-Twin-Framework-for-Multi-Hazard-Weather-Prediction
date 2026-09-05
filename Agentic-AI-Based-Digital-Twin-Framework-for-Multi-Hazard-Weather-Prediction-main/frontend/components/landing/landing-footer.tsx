import Link from 'next/link'
import { Radar } from 'lucide-react'
import { PLATFORM_NAME } from '@/lib/constants/navigation'

export function LandingFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-6xl px-6 py-12 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Radar className="size-4 text-primary" aria-hidden="true" />
            <span className="font-semibold text-sm">{PLATFORM_NAME}</span>
          </div>
          <p className="text-xs text-muted-foreground max-w-sm leading-relaxed">
            Agentic AI based Digital Twin framework for rainfall prediction and extreme weather
            intelligence. Developed during an IIT Mandi research internship.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Footer">
          <Link href="/dashboard" className="text-muted-foreground hover:text-foreground">
            Dashboard
          </Link>
          <Link href="/map" className="text-muted-foreground hover:text-foreground">
            GIS Map
          </Link>
          <Link href="/digital-twin" className="text-muted-foreground hover:text-foreground">
            Digital Twin
          </Link>
          <Link href="/research" className="text-muted-foreground hover:text-foreground">
            Research
          </Link>
        </nav>
      </div>
      <div className="border-t border-border py-4 text-center text-xs text-muted-foreground">
        Research prototype. Data shown is representative and not for operational use.
      </div>
    </footer>
  )
}

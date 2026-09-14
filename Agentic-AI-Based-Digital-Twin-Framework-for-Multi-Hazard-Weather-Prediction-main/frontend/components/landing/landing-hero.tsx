'use client'

import Link from 'next/link'
import Image from 'next/image'
import { motion } from 'framer-motion'
import { ArrowRight, Radar, Satellite, BrainCircuit, ShieldAlert } from 'lucide-react'
import { PLATFORM_NAME } from '@/lib/constants/navigation'

const RAIN_DROPS = Array.from({ length: 26 }, (_, i) => ({
  left: `${(i * 137) % 100}%`,
  delay: `${(i * 0.37) % 4}s`,
  duration: `${2.4 + ((i * 0.53) % 2)}s`,
}))

export function LandingHero() {
  return (
    <section className="relative overflow-hidden min-h-svh flex flex-col">
      {/* Background earth */}
      <div className="absolute inset-0">
        <Image
          src="/images/earth-hero.png"
          alt="Digital Twin Earth Hero"
          fill
          sizes="100vw"
          unoptimized
          priority
          className="object-cover opacity-60"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/70 via-background/40 to-background" />
      </div>

      {/* Rain animation */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        {RAIN_DROPS.map((d, i) => (
          <span
            key={i}
            className="absolute top-0 w-px h-16 bg-gradient-to-b from-transparent via-primary/50 to-transparent"
            style={{
              left: d.left,
              animation: `rain-fall ${d.duration} linear ${d.delay} infinite`,
            }}
          />
        ))}
      </div>

      {/* Nav */}
      <header className="relative z-10 flex items-center justify-between px-6 lg:px-12 h-16">
        <div className="flex items-center gap-2.5">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/15 border border-primary/25 text-primary">
            <Radar className="size-4.5" aria-hidden="true" />
          </span>
          <span className="font-semibold tracking-wide">{PLATFORM_NAME}</span>
        </div>
        <nav className="flex items-center gap-4" aria-label="Landing">
          <Link
            href="/auth"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Sign in
          </Link>
          <Link
            href="/dashboard"
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Open Platform
          </Link>
        </nav>
      </header>

      {/* Hero content */}
      <div className="relative z-10 flex-1 flex items-center px-6 lg:px-12 py-16">
        <div className="max-w-3xl">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            className="inline-flex items-center gap-2 rounded-full glass px-3 py-1.5 text-xs text-muted-foreground mb-6"
          >
            <span className="size-1.5 rounded-full bg-success animate-pulse" />
            Active Development
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.1 }}
            className="text-4xl md:text-6xl font-semibold leading-tight text-balance"
          >
            Agentic AI Digital Twin for{' '}
            <span className="text-primary">Extreme Weather Intelligence</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="mt-6 text-base md:text-lg text-muted-foreground leading-relaxed text-pretty max-w-2xl"
          >
            India&apos;s next-generation disaster intelligence platform — fusing satellite
            observation, hydrology, terrain, population and deep learning into a living Digital
            Twin that predicts rainfall, cloudbursts, floods and landslides before they strike.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.3 }}
            className="mt-8 flex flex-wrap items-center gap-3"
          >
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Launch Dashboard
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link
              href="/map"
              className="inline-flex items-center gap-2 rounded-lg glass px-5 py-2.5 text-sm font-medium hover:border-primary/40 transition-colors"
            >
              Explore GIS Map
            </Link>
          </motion.div>

          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.5 }}
            className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl"
          >
            {[
              { icon: Satellite, label: '17+ data sources', sub: 'ERA5, GPM, MODIS, NDVI' },
              { icon: BrainCircuit, label: '14 model families', sub: 'ML → DL → Transformers' },
              { icon: ShieldAlert, label: '4 hazard engines', sub: 'Rain, cloudburst, flood, slide' },
            ].map((f) => (
              <li key={f.label} className="glass rounded-xl p-3 flex items-start gap-2.5">
                <f.icon className="size-4 text-primary mt-0.5 shrink-0" aria-hidden="true" />
                <span>
                  <span className="block text-sm font-medium">{f.label}</span>
                  <span className="block text-xs text-muted-foreground">{f.sub}</span>
                </span>
              </li>
            ))}
          </motion.ul>
        </div>
      </div>
    </section>
  )
}

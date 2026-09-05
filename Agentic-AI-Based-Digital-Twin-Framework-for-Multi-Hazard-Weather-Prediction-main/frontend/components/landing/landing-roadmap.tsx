'use client'

import { motion } from 'framer-motion'
import { Check, Loader2, Circle } from 'lucide-react'
import { PIPELINE_STAGES } from '@/lib/mock/data'
import { cn } from '@/lib/utils'

export function LandingRoadmap() {
  return (
    <section className="border-y border-border bg-card/40">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-2xl mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">
            Research Roadmap
          </p>
          <h2 className="text-3xl font-semibold text-balance">
            From raw datasets to an early warning platform
          </h2>
          <p className="text-muted-foreground mt-3 leading-relaxed">
            Each stage of the pipeline builds toward a fully agentic Digital Twin decision-support
            system for Himachal Pradesh and beyond.
          </p>
        </div>

        <ol className="relative flex flex-col gap-0">
          {PIPELINE_STAGES.map((stage, i) => (
            <motion.li
              key={stage.name}
              initial={{ opacity: 0, x: -12 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04 }}
              className="relative flex gap-4 pb-8 last:pb-0"
            >
              {i < PIPELINE_STAGES.length - 1 && (
                <span
                  className={cn(
                    'absolute left-[15px] top-8 bottom-0 w-px',
                    stage.status === 'complete' ? 'bg-primary/50' : 'bg-border',
                  )}
                  aria-hidden="true"
                />
              )}
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-full border z-10',
                  stage.status === 'complete' && 'bg-primary/15 border-primary/40 text-primary',
                  stage.status === 'active' && 'bg-warning/15 border-warning/40 text-warning',
                  stage.status === 'upcoming' &&
                    'bg-secondary border-border text-muted-foreground',
                )}
              >
                {stage.status === 'complete' ? (
                  <Check className="size-4" aria-hidden="true" />
                ) : stage.status === 'active' ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Circle className="size-3" aria-hidden="true" />
                )}
              </span>
              <div className="pt-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-medium">{stage.name}</h3>
                  <span
                    className={cn(
                      'rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide',
                      stage.status === 'complete' && 'bg-primary/15 text-primary',
                      stage.status === 'active' && 'bg-warning/15 text-warning',
                      stage.status === 'upcoming' && 'bg-secondary text-muted-foreground',
                    )}
                  >
                    {stage.status === 'complete'
                      ? 'Complete'
                      : stage.status === 'active'
                        ? 'In Progress'
                        : 'Planned'}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground mt-1 leading-relaxed max-w-xl">
                  {stage.description}
                </p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  )
}

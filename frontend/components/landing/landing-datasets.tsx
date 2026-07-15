'use client'

import { motion } from 'framer-motion'
import { Database } from 'lucide-react'
import { DATASETS } from '@/lib/mock/data'

export function LandingDatasets() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="max-w-2xl mb-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">
          Data Foundation
        </p>
        <h2 className="text-3xl font-semibold text-balance">
          A multi-source master dataset already collected
        </h2>
        <p className="text-muted-foreground mt-3 leading-relaxed">
          Seventeen automated collectors continuously ingest weather reanalysis, satellite
          precipitation, vegetation indices, hydrology, terrain, census and disaster history.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {DATASETS.slice(0, 12).map((d, i) => (
          <motion.div
            key={d.name}
            initial={{ opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.04 }}
            className="glass rounded-xl p-4 flex items-start gap-3"
          >
            <Database className="size-4 text-primary mt-0.5 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{d.name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {d.source} · {d.records} records · {d.resolution}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

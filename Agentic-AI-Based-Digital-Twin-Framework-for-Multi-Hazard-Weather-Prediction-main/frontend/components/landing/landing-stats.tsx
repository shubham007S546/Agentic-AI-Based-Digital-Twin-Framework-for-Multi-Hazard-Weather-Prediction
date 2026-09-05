'use client'

import { motion } from 'framer-motion'

const STATS = [
  { value: '24M+', label: 'Records collected' },
  { value: '312', label: 'Engineered features' },
  { value: '8.7 GB', label: 'Master dataset' },
  { value: '6/14', label: 'Models trained' },
  { value: '12', label: 'Districts covered' },
  { value: '72h', label: 'Prediction horizon' },
]

export function LandingStats() {
  return (
    <section className="border-y border-border bg-card/40">
      <div className="mx-auto max-w-6xl px-6 py-10 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-6">
        {STATS.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.06 }}
            className="text-center"
          >
            <p className="text-2xl font-semibold text-primary tabular-nums">{s.value}</p>
            <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

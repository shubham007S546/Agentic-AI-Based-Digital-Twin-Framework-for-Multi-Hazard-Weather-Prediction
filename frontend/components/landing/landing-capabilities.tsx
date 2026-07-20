'use client'

import { motion } from 'framer-motion'
import {
  CloudRain,
  Globe,
  Brain,
  Bot,
  Map,
  Siren,
} from 'lucide-react'

const CAPABILITIES = [
  {
    icon: CloudRain,
    title: 'Rainfall & Cloudburst Prediction',
    body: 'Multi-horizon precipitation forecasting from classical ML to Temporal Fusion Transformers, tuned on Himalayan monsoon dynamics.',
  },
  {
    icon: Map,
    title: 'Map-First GIS Workspace',
    body: 'A live geospatial canvas with satellite, terrain, hydrology, infrastructure and AI risk layers — the map is the platform.',
  },
  {
    icon: Globe,
    title: 'Digital Twin',
    body: 'A living virtual replica of terrain, rivers and infrastructure enabling historical replay and future scenario simulation.',
  },
  {
    icon: Brain,
    title: 'Explainable AI',
    body: 'SHAP values, attention heatmaps and variable importance make every prediction transparent to scientists and officials.',
  },
  {
    icon: Bot,
    title: 'Agentic AI Assistant',
    body: 'Autonomous agents that monitor data streams, reason about risk, answer questions and draft situational reports.',
  },
  {
    icon: Siren,
    title: 'Early Warning System',
    body: 'Village-level alerting with confidence intervals and lead times up to 72 hours for disaster management authorities.',
  },
]

export function LandingCapabilities() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="max-w-2xl mb-12">
        <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">
          Platform Capabilities
        </p>
        <h2 className="text-3xl font-semibold text-balance">
          Not a weather dashboard. A complete disaster intelligence system.
        </h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {CAPABILITIES.map((c, i) => (
          <motion.article
            key={c.title}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.07 }}
            className="glass rounded-xl p-6 hover:border-primary/30 transition-colors"
          >
            <span className="flex size-10 items-center justify-center rounded-lg bg-primary/15 text-primary mb-4">
              <c.icon className="size-5" aria-hidden="true" />
            </span>
            <h3 className="font-medium mb-2">{c.title}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{c.body}</p>
          </motion.article>
        ))}
      </div>
    </section>
  )
}

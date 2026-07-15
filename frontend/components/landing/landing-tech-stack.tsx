'use client'

import { motion } from 'framer-motion'

const STACK = {
  'Data & Modelling': ['Python', 'Pandas', 'Scikit-learn', 'XGBoost', 'PyTorch', 'Optuna'],
  'Deep Learning': ['LSTM', 'GRU', 'TCN', 'Transformer', 'Informer', 'TFT'],
  'Geospatial': ['MapLibre GL', 'GDAL', 'Rasterio', 'GeoPandas', 'DEM Analysis'],
  'Frontend': ['Next.js', 'React 19', 'TypeScript', 'Tailwind CSS', 'Framer Motion', 'Recharts'],
}

export function LandingTechStack() {
  return (
    <section className="border-t border-border bg-card/40">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-2xl mb-12">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">
            Technology
          </p>
          <h2 className="text-3xl font-semibold text-balance">Built on a modern research stack</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {Object.entries(STACK).map(([group, items], gi) => (
            <motion.div
              key={group}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: gi * 0.08 }}
            >
              <h3 className="text-sm font-medium mb-3 text-primary">{group}</h3>
              <ul className="flex flex-wrap gap-1.5">
                {items.map((item) => (
                  <li
                    key={item}
                    className="rounded-md bg-secondary/70 border border-border px-2.5 py-1 text-xs text-muted-foreground"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

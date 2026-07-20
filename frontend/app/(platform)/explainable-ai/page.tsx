import type { Metadata } from 'next'
import { Brain, Layers, Target, Sigma } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { StatCard } from '@/components/shared/stat-card'
import {
  GlobalImportancePanel,
  LocalExplanationPanel,
  AttentionMapPanel,
  ModelCardPanel,
} from '@/components/xai/xai-explorer'

export const metadata: Metadata = {
  title: 'Explainable AI | VARUNA',
  description: 'SHAP attribution, attention maps and model governance for hazard prediction models.',
}

export default function ExplainableAIPage() {
  return (
    <div className="p-4 lg:p-6 flex flex-col gap-6">
      <PageHeader
        title="Explainable AI"
        description="Understand why the models predict what they predict — global SHAP attribution, per-prediction force decomposition and transformer attention analysis."
      />

      <section aria-label="Explainability summary" className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Method" value="SHAP" icon={Brain} sub="TreeSHAP · exact values" />
        <StatCard label="Features Analyzed" value={312} icon={Layers} sub="Engineered feature space" />
        <StatCard label="Top Driver" value="Rain t-1h" icon={Target} sub="16.4% of mean attribution" />
        <StatCard label="Fidelity" value="0.94" icon={Sigma} sub="Kernel vs Tree agreement" tone="success" />
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GlobalImportancePanel />
        <LocalExplanationPanel />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <AttentionMapPanel />
        <ModelCardPanel />
      </div>
    </div>
  )
}

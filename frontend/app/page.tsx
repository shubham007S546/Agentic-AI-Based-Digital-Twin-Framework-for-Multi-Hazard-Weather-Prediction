import type { Metadata } from 'next'
import { LandingHero } from '@/components/landing/landing-hero'
import { LandingStats } from '@/components/landing/landing-stats'
import { LandingRoadmap } from '@/components/landing/landing-roadmap'
import { LandingDatasets } from '@/components/landing/landing-datasets'
import { LandingCapabilities } from '@/components/landing/landing-capabilities'
import { LandingTechStack } from '@/components/landing/landing-tech-stack'
import { LandingFooter } from '@/components/landing/landing-footer'

export const metadata: Metadata = {
  title: 'VARUNA | Agentic AI Digital Twin for Extreme Weather Intelligence',
  description:
    'India&apos;s next-generation AI-powered disaster intelligence platform. Rainfall prediction, cloudburst, flood and landslide intelligence powered by a Digital Twin and Agentic AI. IIT Mandi Research.',
}

export default function LandingPage() {
  return (
    <div className="min-h-svh bg-background">
      <LandingHero />
      <LandingStats />
      <LandingCapabilities />
      <LandingRoadmap />
      <LandingDatasets />
      <LandingTechStack />
      <LandingFooter />
    </div>
  )
}

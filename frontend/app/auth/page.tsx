import type { Metadata } from 'next'
import Link from 'next/link'
import { Radar } from 'lucide-react'
import { AuthForm } from '@/components/auth/auth-form'
import { PLATFORM_NAME, PLATFORM_TAGLINE } from '@/lib/constants/navigation'

export const metadata: Metadata = {
  title: 'Sign In | VARUNA',
  description: 'Sign in to the VARUNA disaster intelligence platform.',
}

export default function AuthPage() {
  return (
    <main className="min-h-svh flex flex-col items-center justify-center p-4 bg-background">
      <div className="w-full max-w-sm flex flex-col gap-6">
        <div className="flex flex-col items-center text-center gap-2">
          <Link href="/" className="flex items-center gap-2" aria-label="VARUNA home">
            <span className="flex size-10 items-center justify-center rounded-xl bg-primary/15 border border-primary/25">
              <Radar className="size-5 text-primary" aria-hidden="true" />
            </span>
          </Link>
          <div>
            <h1 className="text-lg font-semibold">{PLATFORM_NAME}</h1>
            <p className="text-xs text-muted-foreground">{PLATFORM_TAGLINE}</p>
          </div>
        </div>

        <AuthForm />

        <p className="text-center text-[11px] text-muted-foreground">
          <Link href="/" className="text-primary hover:underline">
            Back to overview
          </Link>
          {' · IIT Mandi Research Platform'}
        </p>
      </div>
    </main>
  )
}

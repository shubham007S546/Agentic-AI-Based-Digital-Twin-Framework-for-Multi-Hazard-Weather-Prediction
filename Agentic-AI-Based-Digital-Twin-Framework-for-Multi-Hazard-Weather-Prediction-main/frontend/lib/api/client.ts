/**
 * lib/api/client.ts
 * Base API fetcher with auth injection, error normalization,
 * and graceful fallback to mock data when backend is unreachable.
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('access_token')
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const method = (options.method || 'GET').toUpperCase()
  const isServer = typeof window === 'undefined'

  const fetchOptions: RequestInit = {
    ...options,
    headers,
  }

  // Apply next revalidation only on server for GET requests
  if (isServer && method === 'GET' && !('cache' in options)) {
    ;(fetchOptions as any).next = { revalidate: 30 }
  }

  const res = await fetch(`${BASE_URL}${path}`, fetchOptions)

  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new ApiError(res.status, text)
  }

  return res.json() as Promise<T>
}

/**
 * Wraps a fetch in a try/catch and returns mock fallback on any error.
 * Logs the failure in development for visibility.
 */
export async function fetchWithFallback<T>(
  fetcher: () => Promise<T>,
  fallback: T,
): Promise<T> {
  try {
    return await fetcher()
  } catch (err) {
    if (process.env.NODE_ENV === 'development') {
      console.warn('[API] Backend unreachable — using mock data:', err)
    }
    return fallback
  }
}

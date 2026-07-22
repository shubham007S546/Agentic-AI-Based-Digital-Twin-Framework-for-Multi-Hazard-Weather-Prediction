/**
 * lib/api/auth.ts
 * API service for authentication endpoints.
 */
import { apiFetch } from './client'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface UserProfile {
  id: string
  email: string
  full_name: string
  role: string
  organization?: string
  department?: string
  is_active: boolean
  is_verified: boolean
  last_login?: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RequestAccessData {
  full_name: string
  email: string
  institution: string
  department: string
  purpose: string
  research_area?: string
}

export interface RequestAccessResponse {
  id: string
  email: string
  status: string
  created_at: string
}

export async function login(credentials: LoginCredentials): Promise<TokenResponse> {
  const res = await apiFetch<{ data: TokenResponse }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
  return res.data
}

export async function logout(): Promise<void> {
  await apiFetch('/auth/logout', { method: 'POST' })
}

export async function getMe(): Promise<UserProfile> {
  const res = await apiFetch<{ data: UserProfile }>('/auth/me', {
    method: 'GET',
    next: { revalidate: 0 }, // Never cache the current user profile
  })
  return res.data
}

export async function requestAccess(data: RequestAccessData): Promise<RequestAccessResponse> {
  const res = await apiFetch<{ data: RequestAccessResponse, message: string }>('/auth/request-access', {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return res.data
}

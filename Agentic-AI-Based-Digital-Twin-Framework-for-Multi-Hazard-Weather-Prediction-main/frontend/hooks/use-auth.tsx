'use client'

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { login as apiLogin, logout as apiLogout, getMe, UserProfile, LoginCredentials, TokenResponse } from '@/lib/api/auth'
import { ApiError } from '@/lib/api/client'

interface AuthContextType {
  user: UserProfile | null
  token: string | null
  isLoading: boolean
  login: (credentials: LoginCredentials) => Promise<TokenResponse>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Helper to manage the access token in both localStorage (for API client) 
// and cookies (for Next.js middleware)
function setTokenStorage(token: string | null) {
  if (typeof window === 'undefined') return
  
  if (token) {
    localStorage.setItem('access_token', token)
    document.cookie = `access_token=${token}; path=/; max-age=86400; SameSite=Lax`
  } else {
    localStorage.removeItem('access_token')
    document.cookie = `access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const router = useRouter()

  useEffect(() => {
    // Attempt to load the user profile if we have a token stored
    const storedToken = localStorage.getItem('access_token')
    if (storedToken) {
      setToken(storedToken)
      getMe()
        .then((profile) => setUser(profile))
        .catch((err) => {
          // If the token is invalid/expired, clear it
          if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
            setTokenStorage(null)
            setToken(null)
          }
        })
        .finally(() => setIsLoading(false))
    } else {
      setIsLoading(false)
    }
  }, [])

  const login = async (credentials: LoginCredentials) => {
    const data = await apiLogin(credentials)
    setTokenStorage(data.access_token)
    setToken(data.access_token)
    // Fetch user profile immediately after login
    const profile = await getMe()
    setUser(profile)
    return data
  }

  const logout = async () => {
    try {
      if (token) {
        await apiLogout()
      }
    } catch (err) {
      console.warn('Logout API failed, continuing local logout', err)
    } finally {
      setTokenStorage(null)
      setToken(null)
      setUser(null)
      router.push('/auth')
    }
  }

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

import { createContext, useCallback, useContext, useEffect, useState } from 'react'

import { api, clearToken, getToken, setToken } from '../api/client'
import type { User } from '../api/types'

export interface SignUpResult {
  email: string
  /** False when no mailer is configured — the UI must not say "check your
   *  inbox" for a link that was never sent. */
  verification_sent: boolean
}

interface AuthState {
  user: User | null
  checking: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, displayName: string) => Promise<SignUpResult>
  signOut: () => Promise<void>
  adopt: (token: string) => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [checking, setChecking] = useState(!!getToken())

  useEffect(() => {
    if (!getToken()) return
    api<User>('auth/me')
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecking(false))
  }, [])

  const refresh = useCallback(async () => {
    setUser(await api<User>('auth/me'))
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await api<{ token: string; user: User }>('auth/login', {
      method: 'POST',
      body: { email, password },
    })
    setToken(result.token)
    setUser(result.user)
  }, [])

  const signUp = useCallback(
    async (email: string, password: string, displayName: string) => {
      // no session yet — the emailed link is what proves the address
      return api<SignUpResult>('auth/signup', {
        method: 'POST',
        body: { email, password, display_name: displayName },
      })
    },
    [],
  )

  /** Adopt a token handed back by the OAuth or verification hop. */
  const adopt = useCallback(async (token: string) => {
    setToken(token)
    setChecking(true)
    try {
      setUser(await api<User>('auth/me'))
    } finally {
      setChecking(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    await api('auth/logout', { method: 'POST' }).catch(() => undefined)
    clearToken()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, checking, signIn, signUp, signOut, adopt, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

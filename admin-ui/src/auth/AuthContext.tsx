import { createContext, useCallback, useContext, useEffect, useState } from 'react'

import { api, clearToken, getToken, setToken } from '../api/client'
import type { User } from '../api/types'

interface AuthState {
  user: User | null
  checking: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
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

  const login = useCallback(async (username: string, password: string) => {
    const result = await api<{ token: string; user: User }>('auth/login', {
      method: 'POST',
      body: { username, password },
    })
    setToken(result.token)
    setUser(result.user)
  }, [])

  const logout = useCallback(async () => {
    await api('auth/logout', { method: 'POST' }).catch(() => undefined)
    clearToken()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

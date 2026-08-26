import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api/client'
import { setToken } from '../api/client'
import type { User } from '../api/types'
import { AuthShell } from './AuthShell'
import { useAuth } from './AuthContext'

export function VerifyPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { refresh } = useAuth()
  const [error, setError] = useState('')

  useEffect(() => {
    const token = params.get('token')
    if (!token) {
      setError('That link is missing its token.')
      return
    }
    api<{ token: string; user: User }>('auth/verify', { method: 'POST', body: { token } })
      .then(async (result) => {
        setToken(result.token)
        await refresh()
        navigate('/browse', { replace: true })
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'That link did not work.'))
  }, [params, navigate, refresh])

  if (!error) {
    return (
      <div className="screen-center">
        <p className="muted">Confirming your email…</p>
      </div>
    )
  }

  return (
    <AuthShell eyebrow="Confirmation" heading="That link didn't work">
      <div className="auth-card">
        <div className="error-banner" role="alert">
          {error}
        </div>
        <p className="muted auth-note">
          Links expire after 48 hours. Head to sign-in and ask for a fresh one.
        </p>
        <button className="btn btn-primary" onClick={() => navigate('/signin')}>
          Back to sign in
        </button>
      </div>
    </AuthShell>
  )
}

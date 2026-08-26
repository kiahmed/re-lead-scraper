import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { AuthShell } from './AuthShell'
import { ProviderButtons } from './ProviderButtons'
import { useAuth } from './AuthContext'

export function SignInPage() {
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/browse'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await signIn(email, password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  async function resend() {
    const result = await api<{ email_configured: boolean }>('auth/resend-verification', {
      method: 'POST',
      body: { email },
    }).catch(() => ({ email_configured: false }))
    setNotice(
      result.email_configured
        ? 'If that address needs confirming, a new link is on its way.'
        : "Email isn't switched on for this site yet — sign in with your password instead.",
    )
  }

  return (
    <AuthShell eyebrow="Deal board" heading="Sign in to your board">
      <form className="auth-card" onSubmit={onSubmit}>
        <ProviderButtons next={from} />
        <label className="field">
          <span>Email</span>
          <input
            className="input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        {notice && <div className="ok-banner">{notice}</div>}
        <button className="btn btn-primary" disabled={busy || !email || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="muted auth-note">
          New here? <Link to="/signup">Create an account</Link>. Didn't get your confirmation
          email?{' '}
          <button type="button" className="link-btn" onClick={resend}>
            Send it again
          </button>
          .
        </p>
      </form>
    </AuthShell>
  )
}

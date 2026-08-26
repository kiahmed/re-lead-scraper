import { useState } from 'react'
import { Link } from 'react-router-dom'

import { AuthShell } from './AuthShell'
import { ProviderButtons } from './ProviderButtons'
import { useAuth } from './AuthContext'

export function SignUpPage() {
  const { signUp } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [created, setCreated] = useState<{ verification_sent: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      setCreated(await signUp(email, password, displayName))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-up failed')
    } finally {
      setBusy(false)
    }
  }

  if (created) {
    // Only promise an email when one actually went out.
    return created.verification_sent ? (
      <AuthShell eyebrow="One step left" heading="Check your email">
        <div className="auth-card">
          <p>
            We sent a confirmation link to <strong>{email}</strong>. Open it and your board is
            ready.
          </p>
          <p className="muted auth-note">
            The link works for 48 hours. Already confirmed? <Link to="/signin">Sign in</Link>.
          </p>
        </div>
      </AuthShell>
    ) : (
      <AuthShell eyebrow="Account created" heading="You're in — sign in to start">
        <div className="auth-card">
          <p>
            Your account is ready. Email isn't switched on for this site yet, so there's no
            confirmation link to open — sign in with the password you just chose.
          </p>
          <p className="muted auth-note">
            You can browse the board, keep notes, and get instant push alerts right away. Email
            alerts unlock once the operator turns email on.
          </p>
          <Link className="btn btn-primary" to="/signin">
            Sign in
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell eyebrow="Deal board" heading="Start your board">
      <form className="auth-card" onSubmit={onSubmit}>
        <ProviderButtons />
        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            autoComplete="name"
            placeholder="What should we call you?"
          />
        </label>
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
            autoComplete="new-password"
            minLength={8}
            required
          />
          <span className="faint auth-hint">At least 8 characters.</span>
        </label>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <button className="btn btn-primary" disabled={busy || !email || password.length < 8}>
          {busy ? 'Creating your board…' : 'Create account'}
        </button>
        <p className="muted auth-note">
          Already have a board? <Link to="/signin">Sign in</Link>.
        </p>
      </form>
    </AuthShell>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from './AuthContext'

/**
 * Lands here after a provider hop. The API hands the session token back in the
 * URL *fragment* — fragments are never sent to a server or written to proxy
 * logs — so the first thing we do is take it and scrub the address bar.
 */
export function OAuthCallback() {
  const { adopt } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
    const token = params.get('token')
    const next = params.get('next') || '/browse'
    window.history.replaceState(null, '', window.location.pathname)

    if (!token) {
      setError('That sign-in link is missing its token. Try signing in again.')
      return
    }
    adopt(token)
      .then(() => navigate(next, { replace: true }))
      .catch(() => setError('We could not finish signing you in. Try again.'))
  }, [adopt, navigate])

  return (
    <div className="screen-center">
      {error ? (
        <>
          <div className="error-banner" role="alert">
            {error}
          </div>
          <button className="btn" onClick={() => navigate('/signin', { replace: true })}>
            Back to sign in
          </button>
        </>
      ) : (
        <p className="muted">Finishing sign-in…</p>
      )}
    </div>
  )
}

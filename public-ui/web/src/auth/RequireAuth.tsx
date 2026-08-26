import { Navigate, useLocation } from 'react-router-dom'

import { getToken } from '../api/client'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { checking } = useAuth()
  const location = useLocation()
  if (!getToken()) {
    // remember where they were headed so sign-in can send them back
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />
  }
  if (checking) return <div className="screen-center muted">Waking the deal board…</div>
  return <>{children}</>
}

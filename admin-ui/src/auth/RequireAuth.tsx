import { Navigate } from 'react-router-dom'

import { getToken } from '../api/client'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { checking } = useAuth()
  if (!getToken()) return <Navigate to="/login" replace />
  if (checking) return <div className="screen-center muted">Waking the API…</div>
  return <>{children}</>
}

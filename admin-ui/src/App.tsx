import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { useMeta } from './api/hooks'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/RequireAuth'
import { useAuth } from './auth/AuthContext'
import { LeadDetailPage } from './pages/LeadDetailPage'
import { LeadListPage } from './pages/LeadListPage'

function AppHeader() {
  const { user, logout } = useAuth()
  const meta = useMeta()
  const navigate = useNavigate()
  const status = meta.data?.pipeline.status

  return (
    <header className="app-header">
      <span className="app-mark">◆ SolJet Leads</span>
      <span className="header-spacer" />
      {status && (
        <span className={`chip ${status === 'in-sync' ? 'cat-seller-finance' : 'cat-fix-flip'}`}>
          {status === 'in-sync' ? '● In sync' : `○ ${status}`}
        </span>
      )}
      <span className="muted">{user?.display_name || user?.username}</span>
      <button
        className="btn"
        onClick={async () => {
          await logout()
          navigate('/login', { replace: true })
        }}
      >
        Sign out
      </button>
    </header>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <AppHeader />
      <main className="app-main">{children}</main>
    </div>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<RequireAuth><Shell><LeadListPage /></Shell></RequireAuth>} />
      <Route path="/leads/:leadId" element={<RequireAuth><Shell><LeadDetailPage /></Shell></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

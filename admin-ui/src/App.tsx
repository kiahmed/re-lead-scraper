import { useEffect, useRef, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { useMeta } from './api/hooks'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/RequireAuth'
import { useAuth } from './auth/AuthContext'
import { LeadDetailPage } from './pages/LeadDetailPage'
import { LeadListPage } from './pages/LeadListPage'
import { SettingsPage } from './pages/SettingsPage'

function HeaderMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onAway(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onAway)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onAway)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  return (
    <div className="menu" ref={ref}>
      <button className="btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        ☰ Menu
      </button>
      {open && (
        <nav className="menu-panel" role="menu" onClick={() => setOpen(false)}>
          <Link role="menuitem" to="/">Leads</Link>
          <Link role="menuitem" to="/settings">Settings</Link>
        </nav>
      )}
    </div>
  )
}

function AppHeader() {
  const { user, logout } = useAuth()
  const meta = useMeta()
  const navigate = useNavigate()
  const status = meta.data?.pipeline.status

  return (
    <header className="app-header">
      <Link to="/" className="app-mark">◆ FlyNest Leads Admin</Link>
      <span className="header-spacer" />
      <HeaderMenu />
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
      <Route path="/settings" element={<RequireAuth><Shell><SettingsPage /></Shell></RequireAuth>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

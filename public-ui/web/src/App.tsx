import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import { useAuth } from './auth/AuthContext'
import { OAuthCallback } from './auth/OAuthCallback'
import { RequireAuth } from './auth/RequireAuth'
import { SignInPage } from './auth/SignInPage'
import { SignUpPage } from './auth/SignUpPage'
import { VerifyPage } from './auth/VerifyPage'
import { PropertyFrieze } from './components/PropertyFrieze'
import { ShareCluster } from './components/ShareCluster'
import { BrowsePage } from './pages/BrowsePage'
import { LeadPage } from './pages/LeadPage'
import { SettingsPage } from './pages/SettingsPage'
import { WorkspacePage } from './pages/WorkspacePage'

function AppHeader() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  return (
    <header className="app-header">
      <div className="app-header-bar">
        <NavLink to="/browse" className="wordmark">
          <span className="wordmark-rule" aria-hidden="true" />
          FlyNest
        </NavLink>

        <nav className="app-nav" aria-label="Main">
          <NavLink to="/browse">Board</NavLink>
          <NavLink to="/workspace">Workspace</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>

        <span className="lead-row-spacer" />
        <ShareCluster />
        <span className="muted app-user">{user?.display_name || user?.email}</span>
        <button
          className="btn btn-sm"
          onClick={async () => {
            await signOut()
            navigate('/signin', { replace: true })
          }}
        >
          Sign out
        </button>
      </div>
      {/* a ground-line band: the wrapper crops to the base of the drawing, so
          it reads as a datum under the nav rather than art behind it */}
      <div className="frieze-band" aria-hidden="true">
        <PropertyFrieze variant="strip" />
      </div>
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

function guarded(element: React.ReactNode) {
  return (
    <RequireAuth>
      <Shell>{element}</Shell>
    </RequireAuth>
  )
}

export function App() {
  return (
    <Routes>
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route path="/verify" element={<VerifyPage />} />
      <Route path="/auth/callback" element={<OAuthCallback />} />
      <Route path="/browse" element={guarded(<BrowsePage />)} />
      <Route path="/leads/:leadId" element={guarded(<LeadPage />)} />
      <Route path="/workspace" element={guarded(<WorkspacePage />)} />
      <Route path="/settings" element={guarded(<SettingsPage />)} />
      <Route path="*" element={<Navigate to="/browse" replace />} />
    </Routes>
  )
}

import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { AuthProvider } from './AuthContext'
import { RequireAuth } from './RequireAuth'

function renderGuarded() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/" element={<RequireAuth><div>secret content</div></RequireAuth>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('RequireAuth', () => {
  it('redirects to /login when no token is stored', () => {
    renderGuarded()
    expect(screen.getByText('login page')).toBeInTheDocument()
    expect(screen.queryByText('secret content')).not.toBeInTheDocument()
  })

  it('renders children when a token exists and /auth/me succeeds', async () => {
    sessionStorage.setItem('soljet_admin_token', 't')
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ username: 'alice', display_name: 'Alice', role: 'admin', is_active: true, last_login_at: '' }), { status: 200 }),
    ))
    renderGuarded()
    expect(await screen.findByText('secret content')).toBeInTheDocument()
  })
})

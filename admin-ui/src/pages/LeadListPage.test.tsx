import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { LeadListResponse } from '../api/types'
import { LeadListPage } from './LeadListPage'

const listResponse: LeadListResponse = {
  items: [
    {
      id: 'facebook_x==',
      authorName: 'Maria G.',
      groupName: 'ATL Wholesalers',
      keywords: ['Atlanta'],
      category: 'Subject-To',
      has_selling_intent: true,
      is_complete: false,
      outreach_skipped: false,
      errorMessage: 'none',
      missing_fields: ['asking_price'],
      stored_at: '2026-08-01T09:12:00+00:00',
      classified_at: '2026-08-01T09:12:30+00:00',
      outreach_at: '2026-08-01T09:13:00+00:00',
      snippet: 'Behind on payments, need out of my Atlanta property…',
    },
  ],
  total: 1,
  page: 1,
  pageSize: 25,
  counts: { 'Subject-To': 1 },
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <LeadListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  sessionStorage.setItem('soljet_admin_token', 'test-token')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url)
    const body = path.includes('/api/meta')
      ? { categories: ['Subject-To', 'Fix & Flip'], required_fields: {}, pipeline: { status: 'in-sync', deployed_at: '', synced_at: '' } }
      : listResponse
    return new Response(JSON.stringify(body), { status: 200 })
  }))
})

describe('LeadListPage', () => {
  it('renders lead rows with author, category, snippet, and count', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Maria G.')).toBeInTheDocument())
    expect(screen.getAllByText('Subject-To').length).toBeGreaterThan(0)
    expect(screen.getByText(/Behind on payments/)).toBeInTheDocument()
    expect(screen.getByText('1 lead')).toBeInTheDocument()
  })

  it('renders category tabs from meta', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('tab', { name: /Fix & Flip/ })).toBeInTheDocument())
    expect(screen.getByRole('tab', { name: /^All/ })).toBeInTheDocument()
  })

  it('shows the incomplete status glyph', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTitle('Incomplete')).toBeInTheDocument())
  })
})

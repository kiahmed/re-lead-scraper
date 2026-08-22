import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
      keep: false,
      cities: ['Atlanta'],
      hoa: 'zero' as const,
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
  city_counts: { Atlanta: 1 },
  hoa_counts: { zero: 1 },
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
  sessionStorage.setItem('flynest_admin_token', 'test-token')
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url)
    const body = path.includes('/api/meta')
      ? { categories: ['Subject-To', 'Fix & Flip'], cities: ['Atlanta', 'All Other Cities'], required_fields: {}, pipeline: { status: 'in-sync', deployed_at: '', synced_at: '' } }
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

describe('LeadListPage row actions', () => {
  it('shows edit and delete buttons per row', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Maria G.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /Edit lead from Maria G./ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Delete lead from Maria G./ })).toBeInTheDocument()
  })

  it('delete asks for confirmation and only deletes after confirm', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Maria G.')).toBeInTheDocument())
    screen.getByRole('button', { name: /Delete lead from Maria G./ }).click()
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument()
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    const deletesBefore = fetchMock.mock.calls.filter((c) => c[1]?.method === 'DELETE').length
    expect(deletesBefore).toBe(0)
    screen.getByRole('button', { name: 'Delete' }).click()
    await waitFor(() => {
      const deletes = fetchMock.mock.calls.filter((c) => c[1]?.method === 'DELETE')
      expect(deletes.length).toBe(1)
      expect(String(deletes[0][0])).toContain('/api/leads/facebook_x')
    })
  })
})

describe('date filters', () => {
  it('presetRange computes windows from local midnight', async () => {
    const { presetRange } = await import('./LeadListPage')
    const now = new Date(2026, 7, 2, 15, 30)          // Aug 2 2026, 3:30pm local
    const midnight = new Date(2026, 7, 2).getTime()
    expect(presetRange('all', now)).toEqual({ from: '', to: '' })
    expect(presetRange('today', now).from).toBe(new Date(midnight).toISOString())
    expect(presetRange('yesterday', now)).toEqual({
      from: new Date(midnight - 86_400_000).toISOString(),
      to: new Date(midnight - 1).toISOString(),
    })
    expect(presetRange('7d', now).from).toBe(new Date(midnight - 7 * 86_400_000).toISOString())
  })

  it('renders the preset selector and custom range inputs', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Maria G.')).toBeInTheDocument())
    const select = screen.getByLabelText('Received date') as HTMLSelectElement
    expect(select.value).toBe('all')
    fireEvent.change(select, { target: { value: 'custom' } })
    expect(screen.getByLabelText('Received from')).toBeInTheDocument()
    expect(screen.getByLabelText('Received to')).toBeInTheDocument()
  })
})

describe('city and HOA filters', () => {
  it('renders both selects with counts and filters by city', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Maria G.')).toBeInTheDocument())
    const city = screen.getByLabelText('City') as HTMLSelectElement
    const hoa = screen.getByLabelText('HOA') as HTMLSelectElement
    expect(city).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Atlanta (1)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'All Other Cities' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'No HOA / $0 (1)' })).toBeInTheDocument()

    fireEvent.change(city, { target: { value: 'Atlanta' } })
    fireEvent.change(hoa, { target: { value: 'zero' } })
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.includes('city=Atlanta') && u.includes('hoa=zero'))).toBe(true)
    })
  })

  it('shows the detected city and HOA badge on a row', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('No HOA')).toBeInTheDocument())
    expect(screen.getByText(/📍\s*Atlanta/)).toBeInTheDocument()  // row badge, not the select
  })
})

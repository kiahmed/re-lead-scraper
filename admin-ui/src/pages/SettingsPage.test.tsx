import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PurgeResult } from '../api/types'
import { SettingsPage, presetCutoff } from './SettingsPage'

const emptyResult: PurgeResult = {
  dry_run: true, matched: 0, purged: 0, would_purge: 0,
  skipped_keep: 0, skipped_activity: 0, skipped_undated: 0,
  matched_span: { oldest: '', newest: '' },
  data_span: { oldest: '2026-08-09T00:00:00+00:00', newest: '2026-08-22T00:00:00+00:00' },
  by_category: {},
}

const hitResult: PurgeResult = {
  ...emptyResult,
  matched: 12, would_purge: 12,
  matched_span: { oldest: '2026-01-05T00:00:00+00:00', newest: '2026-02-20T00:00:00+00:00' },
  by_category: { Others: 8, Regular: 4 },
}

function renderPage(result: PurgeResult) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(result), { status: 200 })))
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => sessionStorage.setItem('flynest_admin_token', 't'))

describe('presetCutoff', () => {
  const now = new Date(2026, 7, 22) // Aug 22 2026, local
  it('computes day and month windows', () => {
    expect(presetCutoff({ label: '30 days', days: 30 }, now)).toBe(
      new Date(2026, 6, 23).toISOString().slice(0, 10),
    )
    expect(presetCutoff({ label: '3 months', months: 3 }, now)).toBe(
      new Date(2026, 4, 22).toISOString().slice(0, 10),
    )
    expect(presetCutoff({ label: '12 months', months: 12 }, now)).toBe(
      new Date(2025, 7, 22).toISOString().slice(0, 10),
    )
  })
})

describe('SettingsPage quick presets', () => {
  it('a preset click fires a dry-run preview with a to-date and no from-date', async () => {
    renderPage(emptyResult)
    screen.getByRole('button', { name: '3 months' }).click()
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body))
    expect(body.dry_run).toBe(true)
    expect(body.from).toBe('')
    expect(body.to).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    // to-date must be ~3 months back, not today
    expect(new Date(body.to).getTime()).toBeLessThan(Date.now() - 60 * 86_400_000)
  })

  it('explains an empty window instead of looking broken', async () => {
    renderPage(emptyResult)
    screen.getByRole('button', { name: '3 months' }).click()
    expect(await screen.findByText(/No leads/)).toBeInTheDocument()
    expect(screen.getByText(/oldest lead is from/)).toBeInTheDocument()
  })

  it('populates the From box from the matched span when leads match', async () => {
    renderPage(hitResult)
    screen.getByRole('button', { name: '12 months' }).click()
    await waitFor(() => expect(screen.getByRole('button', { name: /Purge 12 leads/ })).toBeInTheDocument())
    const fromInput = screen.getByLabelText('From') as HTMLInputElement
    expect(fromInput.value).toBe('2026-01-05')
    const toInput = screen.getByLabelText('To (required)') as HTMLInputElement
    expect(toInput.value).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(screen.getByRole('checkbox', { name: /Others/ })).toBeInTheDocument()
  })
})

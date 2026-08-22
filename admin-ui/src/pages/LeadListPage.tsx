import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useDeleteLead, useLeads, type LeadFilters } from '../api/hooks'
import { useMeta } from '../api/hooks'
import type { LeadSummary } from '../api/types'
import { CategoryChip } from '../components/CategoryChip'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { PencilIcon, TrashIcon } from '../components/Icons'
import { StatusGlyph } from '../components/StatusGlyph'
import { fmtDateTime } from '../lib/format'

const DEFAULT_FILTERS: LeadFilters = {
  q: '', category: '', is_complete: '', from: '', to: '', city: '', hoa: '', page: 1, pageSize: 25,
}

/** HOA states as reported by the API — mirrors the pipeline's own patterns.
 * "Not mentioned" is kept separate from "$0" on purpose: silence is not a
 * claim that there is no HOA. */
const HOA_OPTIONS: { value: string; label: string }[] = [
  { value: 'zero', label: 'No HOA / $0' },
  { value: 'has', label: 'Has HOA fee' },
  { value: 'none', label: 'HOA not mentioned' },
]

export type DatePreset = 'all' | 'today' | 'yesterday' | '7d' | '30d' | 'custom'

/** Preset windows on the "Received & passed filter" timestamp (stored_at),
 * computed from local midnight so "Today" matches the user's calendar. */
export function presetRange(preset: DatePreset, now = new Date()): { from: string; to: string } {
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const days = (n: number) => new Date(midnight.getTime() - n * 86_400_000)
  switch (preset) {
    case 'today': return { from: midnight.toISOString(), to: '' }
    case 'yesterday': return { from: days(1).toISOString(), to: new Date(midnight.getTime() - 1).toISOString() }
    case '7d': return { from: days(7).toISOString(), to: '' }
    case '30d': return { from: days(30).toISOString(), to: '' }
    default: return { from: '', to: '' }
  }
}

export function LeadListPage() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [preset, setPreset] = useState<DatePreset>('all')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<LeadSummary | null>(null)
  const { data, isLoading, isError, error, refetch } = useLeads(filters)
  const deleteLead = useDeleteLead()
  const meta = useMeta()
  const navigate = useNavigate()

  const categories = meta.data?.categories ?? Object.keys(data?.counts ?? {})
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1

  function set(partial: Partial<LeadFilters>) {
    setFilters((f) => ({ ...f, page: 1, ...partial }))
  }

  function applyPreset(next: DatePreset) {
    setPreset(next)
    if (next === 'custom') {
      set({ from: customFrom, to: customTo })
    } else {
      set(presetRange(next))
    }
  }

  function applyCustom(from: string, to: string) {
    setCustomFrom(from)
    setCustomTo(to)
    set({ from, to })  // bare dates — API treats `to` as inclusive end of day
  }

  return (
    <div className="list-page">
      <div className="list-toolbar">
        <input
          className="input list-search"
          placeholder="Search posts, authors, groups…"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <select
          className="input"
          value={filters.is_complete}
          onChange={(e) => set({ is_complete: e.target.value })}
          aria-label="Completeness"
        >
          <option value="">All statuses</option>
          <option value="true">Complete</option>
          <option value="false">Incomplete</option>
        </select>
        <select
          className="input"
          value={preset}
          onChange={(e) => applyPreset(e.target.value as DatePreset)}
          aria-label="Received date"
        >
          <option value="all">All time</option>
          <option value="today">Today</option>
          <option value="yesterday">Yesterday</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="custom">Custom range…</option>
        </select>
        {preset === 'custom' && (
          <>
            <input
              className="input"
              type="date"
              value={customFrom}
              onChange={(e) => applyCustom(e.target.value, customTo)}
              aria-label="Received from"
            />
            <input
              className="input"
              type="date"
              value={customTo}
              onChange={(e) => applyCustom(customFrom, e.target.value)}
              aria-label="Received to"
            />
          </>
        )}
        <button className="btn" onClick={() => refetch()}>Refresh</button>
      </div>

      <div className="list-toolbar list-toolbar-2">
        <select
          className="input"
          value={filters.city}
          onChange={(e) => set({ city: e.target.value })}
          aria-label="City"
        >
          <option value="">All cities</option>
          {(meta.data?.cities ?? Object.keys(data?.city_counts ?? {})).map((city) => (
            <option key={city} value={city}>
              {city}{data?.city_counts?.[city] !== undefined ? ` (${data.city_counts[city]})` : ''}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.hoa}
          onChange={(e) => set({ hoa: e.target.value })}
          aria-label="HOA"
        >
          <option value="">Any HOA</option>
          {HOA_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}{data?.hoa_counts?.[opt.value] !== undefined ? ` (${data.hoa_counts[opt.value]})` : ''}
            </option>
          ))}
        </select>
        {(filters.city || filters.hoa) && (
          <button className="btn" onClick={() => set({ city: '', hoa: '' })}>Clear</button>
        )}
      </div>

      <div className="cat-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={filters.category === ''}
          className={filters.category === '' ? 'cat-tab active' : 'cat-tab'}
          onClick={() => set({ category: '' })}
        >
          All <span className="num muted">{Object.values(data?.counts ?? {}).reduce((a, b) => a + b, 0)}</span>
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            role="tab"
            aria-selected={filters.category === cat}
            className={filters.category === cat ? 'cat-tab active' : 'cat-tab'}
            onClick={() => set({ category: cat })}
          >
            {cat} <span className="num muted">{data?.counts?.[cat] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="list-body">
        {isLoading && <div className="screen-center muted">Loading leads…</div>}
        {isError && <div className="error-banner">Failed to load leads: {(error as Error).message}</div>}
        {data && data.items.length === 0 && (
          <div className="screen-center muted">No leads match the current filters.</div>
        )}
        {data?.items.map((lead) => (
          <article
            key={lead.id}
            className="lead-row"
            tabIndex={0}
            onClick={() => navigate(`/leads/${encodeURIComponent(lead.id)}`)}
            onKeyDown={(e) => e.key === 'Enter' && navigate(`/leads/${encodeURIComponent(lead.id)}`)}
          >
            <div className="lead-row-head">
              <strong>{lead.authorName || 'Unknown author'}</strong>
              <span className="muted">· {lead.groupName}</span>
              <CategoryChip category={lead.category} />
              <StatusGlyph {...lead} />
              {lead.cities.length > 0 && (
                <span className="muted">📍 {lead.cities.join(', ')}</span>
              )}
              {lead.hoa !== 'none' && (
                <span className={lead.hoa === 'zero' ? 'chip hoa-zero' : 'chip hoa-has'}>
                  {lead.hoa === 'zero' ? 'No HOA' : 'HOA'}
                </span>
              )}
              <span className="muted num lead-row-time">{fmtDateTime(lead.stored_at)}</span>
              <span className="row-actions">
                <button
                  className="icon-btn"
                  aria-label={`Edit lead from ${lead.authorName}`}
                  title="Edit"
                  onClick={(e) => {
                    e.stopPropagation()
                    navigate(`/leads/${encodeURIComponent(lead.id)}?edit=1`)
                  }}
                >
                  <PencilIcon />
                </button>
                <button
                  className="icon-btn icon-btn-danger"
                  aria-label={`Delete lead from ${lead.authorName}`}
                  title="Delete"
                  onClick={(e) => {
                    e.stopPropagation()
                    setDeleteTarget(lead)
                  }}
                >
                  <TrashIcon />
                </button>
              </span>
            </div>
            <p className="lead-row-snippet">{lead.snippet}</p>
          </article>
        ))}
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title="Delete lead?"
          message={`This permanently removes the lead from ${deleteTarget.authorName || 'unknown author'} and all its notes. This cannot be undone.`}
          busy={deleteLead.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() =>
            deleteLead.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) })
          }
        />
      )}

      <div className="list-footer">
        <span className="muted num">
          {data ? `${data.total} lead${data.total === 1 ? '' : 's'}` : ''}
        </span>
        <div className="pager">
          <button
            className="btn"
            disabled={filters.page <= 1}
            onClick={() => setFilters((f) => ({ ...f, page: f.page - 1 }))}
          >
            ‹ Prev
          </button>
          <span className="num muted">{filters.page} / {totalPages}</span>
          <button
            className="btn"
            disabled={filters.page >= totalPages}
            onClick={() => setFilters((f) => ({ ...f, page: f.page + 1 }))}
          >
            Next ›
          </button>
          <select
            className="input"
            value={filters.pageSize}
            onChange={(e) => set({ pageSize: Number(e.target.value) })}
            aria-label="Rows per page"
          >
            {[10, 25, 50, 100].map((n) => (
              <option key={n} value={n}>{n} / page</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

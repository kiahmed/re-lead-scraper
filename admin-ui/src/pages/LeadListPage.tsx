import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useLeads, type LeadFilters } from '../api/hooks'
import { useMeta } from '../api/hooks'
import { CategoryChip } from '../components/CategoryChip'
import { StatusGlyph } from '../components/StatusGlyph'
import { fmtDateTime } from '../lib/format'

const DEFAULT_FILTERS: LeadFilters = { q: '', category: '', is_complete: '', page: 1, pageSize: 25 }

export function LeadListPage() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const { data, isLoading, isError, error, refetch } = useLeads(filters)
  const meta = useMeta()
  const navigate = useNavigate()

  const categories = meta.data?.categories ?? Object.keys(data?.counts ?? {})
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.pageSize)) : 1

  function set(partial: Partial<LeadFilters>) {
    setFilters((f) => ({ ...f, page: 1, ...partial }))
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
        <button className="btn" onClick={() => refetch()}>Refresh</button>
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
              <span className="muted num lead-row-time">{fmtDateTime(lead.stored_at)}</span>
            </div>
            <p className="lead-row-snippet">{lead.snippet}</p>
          </article>
        ))}
      </div>

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

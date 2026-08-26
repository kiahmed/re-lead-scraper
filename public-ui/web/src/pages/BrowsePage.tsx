import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useLeads, useMeta, useSaveWorkspace, useWorkspace } from '../api/hooks'
import type { LeadSummary } from '../api/types'
import { CategoryChip, HoaChip } from '../components/CategoryChip'
import { NoteIcon, PinIcon, SearchIcon } from '../components/Icons'
import { SpecLedger } from '../components/SpecLedger'
import { relativeTime } from '../lib/format'

const PAGE_SIZE = 25

/** Which numbers to show on a row, per category — the same fields the spokes
 *  need to write a follow-up, so a row shows exactly what a deal turns on. */
function ledgerFields(category: string, required: Record<string, string[]>): string[] {
  const fields = required[category] ?? []
  // location is already carried by the city chip; showing it twice is noise
  return fields.filter((f) => f !== 'location').slice(0, 4)
}

function LeadRow({
  lead,
  required,
  pinned,
  noteCount,
  onPin,
}: {
  lead: LeadSummary
  required: Record<string, string[]>
  pinned: boolean
  noteCount: number
  onPin: () => void
}) {
  return (
    <article className="lead-row">
      <div className="lead-row-head">
        <CategoryChip category={lead.category} />
        {lead.cities.map((city) => (
          <span key={city} className="chip chip-city">
            {city}
          </span>
        ))}
        <HoaChip hoa={lead.hoa} />
        {lead.missing_fields.length > 0 && (
          <span
            className="chip chip-partial"
            title={`Still unknown: ${lead.missing_fields.join(', ')}`}
          >
            {lead.missing_fields.length} unknown
          </span>
        )}
        <span className="lead-row-spacer" />
        <button
          className={`icon-btn${pinned ? ' icon-btn-on' : ''}`}
          onClick={onPin}
          aria-pressed={pinned}
          aria-label={pinned ? 'Unpin from your workspace' : 'Pin to your workspace'}
          title={pinned ? 'Pinned to your workspace' : 'Pin to your workspace'}
        >
          <PinIcon filled={pinned} />
        </button>
        <time className="faint lead-row-time" dateTime={lead.stored_at}>
          {relativeTime(lead.stored_at)}
        </time>
      </div>

      <SpecLedger lead={lead} fields={ledgerFields(lead.category, required)} />

      <Link to={`/leads/${encodeURIComponent(lead.id)}`} className="lead-row-body">
        <p className="lead-row-snippet">{lead.snippet}</p>
      </Link>

      <div className="lead-row-foot faint">
        <span>{lead.authorName || 'Unknown poster'}</span>
        {lead.groupName && <span>· {lead.groupName}</span>}
        {noteCount > 0 && (
          <span className="note-count" title={`${noteCount} of your notes`}>
            <NoteIcon /> {noteCount}
          </span>
        )}
      </div>
    </article>
  )
}

export function BrowsePage() {
  const meta = useMeta()
  const workspace = useWorkspace()
  const saveWorkspace = useSaveWorkspace()

  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [city, setCity] = useState('')
  const [hoa, setHoa] = useState('')
  const [page, setPage] = useState(1)

  const filters = { q, category, city, hoa, is_complete: '', page, pageSize: PAGE_SIZE }
  const leads = useLeads(filters)

  const pinnedIds = useMemo(
    () => new Set((workspace.data?.items ?? []).filter((e) => e.pinned).map((e) => e.lead_id)),
    [workspace.data],
  )
  const noteCounts = workspace.data?.note_counts ?? {}
  const required = meta.data?.required_fields ?? {}

  function reset<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  const total = leads.data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="board">
      <div className="board-controls">
        <div className="search-wrap">
          <span className="search-icon" aria-hidden="true">
            <SearchIcon />
          </span>
          <input
            className="input search-input"
            placeholder="Search posts, posters, groups…"
            value={q}
            onChange={(e) => reset(setQ)(e.target.value)}
            aria-label="Search leads"
          />
        </div>

        <nav className="facet-rail" aria-label="Filter by category">
          <button
            className={`facet${category === '' ? ' facet-on' : ''}`}
            onClick={() => reset(setCategory)('')}
          >
            All <span className="num">{total}</span>
          </button>
          {(meta.data?.categories ?? []).map((name) => {
            const count = leads.data?.counts[name] ?? 0
            if (!count && category !== name) return null
            return (
              <button
                key={name}
                className={`facet${category === name ? ' facet-on' : ''}`}
                onClick={() => reset(setCategory)(category === name ? '' : name)}
              >
                {name} <span className="num">{count}</span>
              </button>
            )
          })}
        </nav>

        <div className="facet-rail facet-rail-2" aria-label="Filter by place and HOA">
          <select
            className="select select-inline"
            value={city}
            onChange={(e) => reset(setCity)(e.target.value)}
            aria-label="Filter by city"
          >
            <option value="">Anywhere</option>
            {(meta.data?.cities ?? []).map((name) => (
              <option key={name} value={name}>
                {name} ({leads.data?.city_counts[name] ?? 0})
              </option>
            ))}
          </select>
          <select
            className="select select-inline"
            value={hoa}
            onChange={(e) => reset(setHoa)(e.target.value)}
            aria-label="Filter by HOA"
          >
            <option value="">Any HOA</option>
            {(meta.data?.hoa_states ?? []).map(({ id, label }) => (
              <option key={id} value={id}>
                {label} ({leads.data?.hoa_counts[id] ?? 0})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="board-body">
        {leads.isPending && <p className="muted board-msg">Reading the board…</p>}
        {leads.isError && (
          <div className="error-banner" role="alert">
            The board didn't load. Refresh to try again.
          </div>
        )}
        {leads.data?.items.length === 0 && (
          <div className="empty-state">
            <p className="title-block">Nothing matches that yet</p>
            <p className="muted">
              Widen the filters, or set an alert so the next one that fits finds you instead.
            </p>
            <Link className="btn btn-brass" to="/settings">
              Set up an alert
            </Link>
          </div>
        )}
        {leads.data?.items.map((lead) => (
          <LeadRow
            key={lead.id}
            lead={lead}
            required={required}
            pinned={pinnedIds.has(lead.id)}
            noteCount={noteCounts[lead.id] ?? 0}
            onPin={() =>
              saveWorkspace.mutate({ leadId: lead.id, pinned: !pinnedIds.has(lead.id) })
            }
          />
        ))}
      </div>

      {total > PAGE_SIZE && (
        <div className="board-foot">
          <span className="muted">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
          </span>
          <div className="pager">
            <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <button
              className="btn btn-sm"
              disabled={page >= lastPage}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

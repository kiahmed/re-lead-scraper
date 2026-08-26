import { Link, useParams } from 'react-router-dom'

import { useLead, useMeta, useSaveWorkspace, useWorkspace } from '../api/hooks'
import type { WorkStatus } from '../api/types'
import { CategoryChip, HoaChip } from '../components/CategoryChip'
import { ExternalIcon, PinIcon } from '../components/Icons'
import { ShareCluster } from '../components/ShareCluster'
import { SpecLedger } from '../components/SpecLedger'
import { absoluteTime, fieldLabel } from '../lib/format'
import { NotesPane } from './panes/NotesPane'

const STATUSES: { id: WorkStatus; label: string }[] = [
  { id: 'new', label: 'New' },
  { id: 'watching', label: 'Watching' },
  { id: 'working', label: 'Working' },
  { id: 'passed', label: 'Passed' },
]

export function LeadPage() {
  const { leadId = '' } = useParams()
  const lead = useLead(leadId)
  const meta = useMeta()
  const workspace = useWorkspace()
  const save = useSaveWorkspace()

  const entry = workspace.data?.items.find((e) => e.lead_id === leadId)
  const required = meta.data?.required_fields ?? {}

  if (lead.isPending) return <p className="muted board-msg">Loading the post…</p>
  if (lead.isError || !lead.data) {
    return (
      <div className="empty-state">
        <p className="title-block">That lead isn't on the board</p>
        <p className="muted">It may have aged out of the window.</p>
        <Link className="btn" to="/browse">
          Back to the board
        </Link>
      </div>
    )
  }

  const data = lead.data
  const fields = (required[data.category] ?? []).filter((f) => f !== 'location')
  const insights = Object.entries(data.location_insights ?? {})

  return (
    <div className="lead-page">
      <div className="lead-topbar">
        <Link to="/browse" className="back-link">
          ← Board
        </Link>
        <span className="lead-row-spacer" />
        <button
          className={`btn btn-sm${entry?.pinned ? ' btn-active' : ''}`}
          onClick={() => save.mutate({ leadId, pinned: !entry?.pinned })}
        >
          <PinIcon filled={!!entry?.pinned} />
          {entry?.pinned ? 'Pinned' : 'Pin'}
        </button>
        <ShareCluster
          compact
          title={`${data.category || 'Lead'} — FlyNest`}
          text={data.content.slice(0, 140)}
        />
      </div>

      <div className="lead-panes">
        <div className="pane deal-pane">
          <div className="lead-row-head">
            <CategoryChip category={data.category} />
            {data.cities.map((city) => (
              <span key={city} className="chip chip-city">
                {city}
              </span>
            ))}
            <HoaChip hoa={data.hoa} />
            <span className="lead-row-spacer" />
            <time className="faint" dateTime={data.stored_at}>
              {absoluteTime(data.stored_at)}
            </time>
          </div>

          <section>
            <h2 className="eyebrow">The numbers</h2>
            <SpecLedger lead={data} fields={fields} />
            <p className="faint spec-key">
              <span className="spec-key-parsed">Underlined</span> values were read out of the
              post — hover to see the words they came from. A ruled blank means the post never
              said.
            </p>
          </section>

          <section>
            <h2 className="eyebrow">The post</h2>
            <blockquote className="post-quote">{data.content}</blockquote>
            <p className="post-meta faint">
              <span>{data.authorName || 'Unknown poster'}</span>
              {data.groupName && <span>· {data.groupName}</span>}
              {data.url && (
                <a href={data.url} target="_blank" rel="noopener noreferrer">
                  <ExternalIcon /> Open the original
                </a>
              )}
            </p>
          </section>

          {data.missing_fields.length > 0 && (
            <section>
              <h2 className="eyebrow">Still unknown</h2>
              <div className="unknown-list">
                {data.missing_fields.map((field) => (
                  <span key={field} className="chip chip-partial">
                    {fieldLabel(field)}
                  </span>
                ))}
              </div>
              <p className="faint">
                These are the gaps you'd have to close with the seller before this deal is
                decidable.
              </p>
            </section>
          )}

          {data.investment_summary && (
            <section>
              <h2 className="eyebrow">Read on the deal</h2>
              <p className="prose">{data.investment_summary}</p>
            </section>
          )}

          {insights.length > 0 && (
            <section>
              <h2 className="eyebrow">Around the address</h2>
              <dl className="insight-grid">
                {insights.map(([key, value]) => (
                  <div key={key} className="insight">
                    <dt className="faint">{fieldLabel(key)}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          <section>
            <h2 className="eyebrow">Where you're at</h2>
            <div className="status-row">
              {STATUSES.map(({ id, label }) => (
                <button
                  key={id}
                  className={`btn btn-sm${(entry?.status ?? 'new') === id ? ' btn-active' : ''}`}
                  onClick={() => save.mutate({ leadId, status: id })}
                >
                  {label}
                </button>
              ))}
            </div>
          </section>
        </div>

        <div className="pane">
          <NotesPane leadId={leadId} />
        </div>
      </div>
    </div>
  )
}

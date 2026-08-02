import { Link } from 'react-router-dom'

import type { LeadDetail } from '../../api/types'
import { Section } from '../../components/Section'
import { fmtDateTime, fmtValue, humanizeKey } from '../../lib/format'

function AttributeList({ lead }: { lead: LeadDetail }) {
  const info = lead.extracted_info
  if (typeof info === 'string') {
    // classifier emitted something unparseable — show it raw rather than hiding it
    return <pre className="mono raw-json">{info || '—'}</pre>
  }
  const entries = Object.entries(info)
  const missing = lead.missing_fields.filter((f) => !(f in info))
  if (entries.length === 0 && missing.length === 0) {
    return <p className="muted">No attributes extracted.</p>
  }
  return (
    <dl className="kv-list">
      {entries.map(([key, value]) => (
        <div className="kv-row" key={key}>
          <dt>{humanizeKey(key)}</dt>
          <dd className="num">{fmtValue(value)}</dd>
        </div>
      ))}
      {missing.map((field) => (
        <div className="kv-row kv-missing" key={field}>
          <dt>{humanizeKey(field)}</dt>
          <dd>missing</dd>
        </div>
      ))}
    </dl>
  )
}

export function DealPane({ lead }: { lead: LeadDetail }) {
  const hasError = lead.errorMessage && lead.errorMessage !== 'none'
  const insights = lead.location_insights ?? {}
  const stats = ['crime_index', 'poverty_rate', 'median_rent_estimate'].filter((k) => insights[k])

  return (
    <div className="pane deal-pane">
      {hasError && <div className="error-banner">Pipeline error: {lead.errorMessage}</div>}

      <Section title="Original post">
        <blockquote className="post-quote">{lead.content || '—'}</blockquote>
        <div className="post-meta muted">
          {lead.keywords.map((k) => (
            <span className="chip cat-others" key={k}>{k}</span>
          ))}
          <span className="mono">{lead.id}</span>
          <span className="num">{fmtDateTime(lead.stored_at)}</span>
        </div>
      </Section>

      <Section title="Contact">
        <dl className="kv-list">
          <div className="kv-row"><dt>Author</dt><dd>{lead.contact.author || lead.authorName || '—'}</dd></div>
          <div className="kv-row"><dt>Phone</dt><dd className="num">{lead.contact.phone || '—'}</dd></div>
          <div className="kv-row"><dt>Email</dt><dd>{lead.contact.email || '—'}</dd></div>
          <div className="kv-row"><dt>DM requested</dt><dd>{lead.contact.dm_requested ? 'Yes' : 'No'}</dd></div>
        </dl>
      </Section>

      <Section title="Extracted attributes">
        <AttributeList lead={lead} />
      </Section>

      <Section title="Investment analysis" defaultOpen={!!lead.is_complete}>
        {lead.is_complete ? (
          <>
            {lead.investment_summary
              ? <p className="analysis-summary">{lead.investment_summary}</p>
              : <p className="muted">No summary produced.</p>}
            {stats.length > 0 && (
              <div className="stat-grid">
                {stats.map((key) => (
                  <div className="stat" key={key}>
                    <span className="eyebrow">{humanizeKey(key)}</span>
                    <span className="stat-value">{insights[key]}</span>
                  </div>
                ))}
              </div>
            )}
            {insights.market_notes && <p className="muted">{insights.market_notes}</p>}
          </>
        ) : (
          <p className="muted">Analysis withheld — outreach incomplete.</p>
        )}
      </Section>

      <div className="pane-footer">
        <Link to="/" className="back-link">‹ Back to list</Link>
      </div>
    </div>
  )
}

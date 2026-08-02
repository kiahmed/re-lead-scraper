import { useState } from 'react'

import { useMeta, usePatchLead } from '../../api/hooks'
import type { LeadDetail } from '../../api/types'
import { humanizeKey } from '../../lib/format'

/** Edit whitelisted lead fields. Extracted attributes edit top-level scalar
 * values; nested structures stay read-only. Numeric-looking input keeps its
 * number type so the classifier JSON stays consistent. */
export function LeadEditForm({ lead, onDone }: { lead: LeadDetail; onDone: () => void }) {
  const meta = useMeta()
  const patchLead = usePatchLead(lead.id)

  const info = typeof lead.extracted_info === 'object' && lead.extracted_info !== null
    ? lead.extracted_info
    : {}
  const scalarKeys = Object.keys(info).filter((k) => typeof info[k] !== 'object' || info[k] === null)

  const [category, setCategory] = useState(lead.category)
  const [authorName, setAuthorName] = useState(lead.authorName)
  const [groupName, setGroupName] = useState(lead.groupName)
  const [phone, setPhone] = useState(lead.contact.phone ?? '')
  const [email, setEmail] = useState(lead.contact.email ?? '')
  const [attrs, setAttrs] = useState<Record<string, string>>(
    Object.fromEntries(scalarKeys.map((k) => [k, info[k] === null ? '' : String(info[k])])),
  )
  const [outreachMessage, setOutreachMessage] = useState(lead.outreach_message)
  const [investmentSummary, setInvestmentSummary] = useState(lead.investment_summary)
  const [error, setError] = useState('')

  function save() {
    const revived: Record<string, unknown> = { ...info }
    for (const [key, value] of Object.entries(attrs)) {
      const original = info[key]
      if (typeof original === 'number' && value.trim() !== '' && !isNaN(Number(value))) {
        revived[key] = Number(value)
      } else if (typeof original === 'boolean') {
        revived[key] = value.trim().toLowerCase() === 'true' || value.trim().toLowerCase() === 'yes'
      } else {
        revived[key] = value
      }
    }
    patchLead.mutate(
      {
        category,
        authorName,
        groupName,
        contact: { ...lead.contact, phone: phone || null, email: email || null },
        extracted_info: revived,
        outreach_message: outreachMessage,
        investment_summary: investmentSummary,
      },
      {
        onSuccess: onDone,
        onError: (err) => setError(err instanceof Error ? err.message : 'save failed'),
      },
    )
  }

  return (
    <div className="pane deal-pane">
      <div className="edit-banner eyebrow">Editing lead</div>
      {error && <div className="error-banner" role="alert">{error}</div>}

      <div className="edit-grid">
        <label>Category
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            {(meta.data?.categories ?? [lead.category]).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>Author
          <input className="input" value={authorName} onChange={(e) => setAuthorName(e.target.value)} />
        </label>
        <label>Group
          <input className="input" value={groupName} onChange={(e) => setGroupName(e.target.value)} />
        </label>
        <label>Phone
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label>Email
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
      </div>

      {scalarKeys.length > 0 && (
        <div>
          <p className="eyebrow">Extracted attributes</p>
          <div className="edit-grid">
            {scalarKeys.map((key) => (
              <label key={key}>{humanizeKey(key)}
                <input
                  className="input"
                  value={attrs[key]}
                  onChange={(e) => setAttrs((a) => ({ ...a, [key]: e.target.value }))}
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <label className="edit-block">Outreach message
        <textarea
          className="input"
          rows={5}
          value={outreachMessage}
          onChange={(e) => setOutreachMessage(e.target.value)}
        />
      </label>
      <label className="edit-block">Investment summary
        <textarea
          className="input"
          rows={4}
          value={investmentSummary}
          onChange={(e) => setInvestmentSummary(e.target.value)}
        />
      </label>

      <div className="edit-actions">
        <button className="btn" onClick={onDone} disabled={patchLead.isPending}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={patchLead.isPending}>
          {patchLead.isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  )
}

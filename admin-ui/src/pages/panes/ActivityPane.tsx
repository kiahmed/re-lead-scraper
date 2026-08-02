import { useState } from 'react'

import { useAddInteraction, useInteractions, usePatchInteraction } from '../../api/hooks'
import type { Interaction, LeadDetail } from '../../api/types'
import { fmtDate, fmtDateTime } from '../../lib/format'

interface TimelineEvent {
  key: string
  at: string
  kind: 'system' | 'interaction'
  label?: string
  interaction?: Interaction
}

function systemEvents(lead: LeadDetail): TimelineEvent[] {
  const events: TimelineEvent[] = []
  if (lead.stored_at) {
    events.push({ key: 'sys-stored', at: lead.stored_at, kind: 'system', label: 'Received & passed filter' })
  }
  if (lead.classified_at) {
    const intent = lead.has_selling_intent ? 'selling intent ✓' : 'no selling intent'
    events.push({
      key: 'sys-classified', at: lead.classified_at, kind: 'system',
      label: `Classified ${lead.category || 'Unclassified'} · ${intent}`,
    })
  }
  if (lead.outreach_at) {
    const label =
      lead.errorMessage && lead.errorMessage !== 'none' ? `Outreach failed: ${lead.errorMessage}`
      : lead.outreach_skipped ? 'Outreach skipped'
      : 'Outreach message drafted'
    events.push({ key: 'sys-outreach', at: lead.outreach_at, kind: 'system', label })
  }
  return events
}

export function ActivityPane({ lead }: { lead: LeadDetail }) {
  const { data, isLoading } = useInteractions(lead.id)
  const addInteraction = useAddInteraction(lead.id)
  const patchInteraction = usePatchInteraction(lead.id)
  const [body, setBody] = useState('')
  const [type, setType] = useState<'note' | 'follow_up'>('note')
  const [followUpAt, setFollowUpAt] = useState('')
  const [copied, setCopied] = useState(false)

  const interactions = data?.items ?? []
  const events: TimelineEvent[] = [
    ...systemEvents(lead),
    ...interactions.map((i) => ({
      key: i.id, at: i.created_at, kind: 'interaction' as const, interaction: i,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at))

  const messageSent = interactions.some((i) => i.type === 'status_change' && i.status === 'sent')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!body.trim()) return
    addInteraction.mutate(
      { type, body, follow_up_at: type === 'follow_up' ? followUpAt : '' },
      { onSuccess: () => { setBody(''); setFollowUpAt('') } },
    )
  }

  async function copyDraft() {
    await navigator.clipboard.writeText(lead.outreach_message)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="pane activity-pane">
      <div className="timeline">
        {events.map((ev) =>
          ev.kind === 'system' ? (
            <div className="timeline-system" key={ev.key}>
              <span className="timeline-dot">●</span>
              <span>{ev.label}</span>
              <span className="muted num">{fmtDateTime(ev.at)}</span>
            </div>
          ) : (
            <InteractionItem
              key={ev.key}
              interaction={ev.interaction!}
              onToggleFollowUp={(i) =>
                patchInteraction.mutate({ id: i.id, follow_up_done: !i.follow_up_done })
              }
            />
          ),
        )}

        {lead.outreach_message && !lead.outreach_skipped && (
          <div className="draft-card">
            <div className="draft-card-head">
              <span className="eyebrow">{messageSent ? 'Outreach message · sent' : 'Outreach draft'}</span>
              <div>
                <button className="btn" onClick={copyDraft}>{copied ? 'Copied ✓' : 'Copy'}</button>
                {!messageSent && (
                  <button
                    className="btn"
                    onClick={() =>
                      addInteraction.mutate({
                        type: 'status_change', body: 'Outreach message marked as sent', status: 'sent',
                      })
                    }
                  >
                    Mark as sent
                  </button>
                )}
              </div>
            </div>
            <p className="draft-body">{lead.outreach_message}</p>
          </div>
        )}

        {isLoading && <p className="muted">Loading activity…</p>}
        {!isLoading && interactions.filter((i) => i.type === 'note').length === 0 && (
          <p className="muted">No notes yet — add the first one below.</p>
        )}
      </div>

      <form className="composer" onSubmit={submit}>
        <div className="composer-row">
          <select
            className="input"
            value={type}
            onChange={(e) => setType(e.target.value as 'note' | 'follow_up')}
            aria-label="Entry type"
          >
            <option value="note">Note</option>
            <option value="follow_up">Follow-up</option>
          </select>
          {type === 'follow_up' && (
            <input
              className="input"
              type="date"
              value={followUpAt}
              onChange={(e) => setFollowUpAt(e.target.value)}
              aria-label="Follow-up date"
            />
          )}
        </div>
        <textarea
          className="input composer-text"
          placeholder={type === 'note' ? 'Add a note…' : 'What needs following up?'}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e)
          }}
          rows={2}
        />
        <button className="btn btn-primary" disabled={!body.trim() || addInteraction.isPending}>
          Save
        </button>
      </form>
    </div>
  )
}

function InteractionItem({
  interaction,
  onToggleFollowUp,
}: {
  interaction: Interaction
  onToggleFollowUp: (i: Interaction) => void
}) {
  if (interaction.type === 'follow_up') {
    const overdue =
      !interaction.follow_up_done &&
      interaction.follow_up_at &&
      interaction.follow_up_at < new Date().toISOString().slice(0, 10)
    return (
      <div className={`followup ${overdue ? 'followup-overdue' : ''}`}>
        <label>
          <input
            type="checkbox"
            checked={interaction.follow_up_done}
            onChange={() => onToggleFollowUp(interaction)}
          />
          <span className={interaction.follow_up_done ? 'followup-done' : ''}>{interaction.body}</span>
        </label>
        <span className="muted num">
          ◔ due {fmtDate(interaction.follow_up_at)}{overdue ? ' · overdue' : ''}
        </span>
      </div>
    )
  }
  if (interaction.type === 'status_change') {
    return (
      <div className="timeline-system">
        <span className="timeline-dot">●</span>
        <span>{interaction.body}</span>
        <span className="muted num">{interaction.author} · {fmtDateTime(interaction.created_at)}</span>
      </div>
    )
  }
  return (
    <div className="note">
      <p>{interaction.body}</p>
      <span className="muted num">
        ✎ {interaction.author} · {fmtDateTime(interaction.created_at)}{interaction.edited ? ' · edited' : ''}
      </span>
    </div>
  )
}

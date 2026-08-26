import { useState } from 'react'

import { usePreview } from '../../api/hooks'
import type { Alert, Channel, Criteria, Meta, SpecClause, SpecOp } from '../../api/types'
import { fieldLabel } from '../../lib/format'

const OPS: { id: SpecOp; label: string }[] = [
  { id: 'lte', label: 'at most' },
  { id: 'gte', label: 'at least' },
  { id: 'between', label: 'between' },
  { id: 'eq', label: 'is' },
  { id: 'ne', label: 'is not' },
  { id: 'contains', label: 'contains' },
]

const DIGESTS = [
  { id: 'instant', label: 'As they land' },
  { id: 'hourly', label: 'Hourly roundup' },
  { id: 'daily', label: 'Daily roundup' },
] as const

function Pills<T extends string>({
  options,
  selected,
  onToggle,
  labelFor,
}: {
  options: T[]
  selected: T[]
  onToggle: (value: T) => void
  labelFor?: (value: T) => string
}) {
  return (
    <div className="pill-row">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className={`pill${selected.includes(option) ? ' pill-on' : ''}`}
          aria-pressed={selected.includes(option)}
          onClick={() => onToggle(option)}
        >
          {labelFor ? labelFor(option) : option}
        </button>
      ))}
    </div>
  )
}

/**
 * The criteria sheet.
 *
 * Laid out like a drawing's schedule table — FIELD / CONDITION / VALUE / IF
 * UNKNOWN — because that last column is the one people get wrong. Most posts
 * don't state every number, so every numeric rule has to say what an
 * unstated value means before it can fire at 3am.
 */
export function AlertBuilder({
  meta,
  initial,
  onSave,
  onCancel,
  saving,
  error,
}: {
  meta: Meta
  initial?: Alert
  onSave: (payload: Partial<Alert>) => void
  onCancel: () => void
  saving: boolean
  error: string
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [criteria, setCriteria] = useState<Criteria>(initial?.criteria ?? { completeness: 'any' })
  const [channels, setChannels] = useState<string[]>(initial?.channels ?? ['email'])
  const [digest, setDigest] = useState<Alert['digest']>(initial?.digest ?? 'instant')
  const [maxPerDay, setMaxPerDay] = useState(initial?.max_per_day ?? 25)
  const [quietFrom, setQuietFrom] = useState(initial?.quiet_hours?.from ?? '')
  const [quietTo, setQuietTo] = useState(initial?.quiet_hours?.to ?? '')
  const preview = usePreview()

  function patch(changes: Partial<Criteria>) {
    setCriteria((prev) => ({ ...prev, ...changes }))
  }

  function toggle<K extends 'categories' | 'cities' | 'hoa' | 'unknowns_required'>(
    key: K,
    value: string,
  ) {
    const current = (criteria[key] ?? []) as string[]
    patch({
      [key]: current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value],
    } as Partial<Criteria>)
  }

  // only specs that mean something for the chosen categories
  const chosen = criteria.categories ?? []
  const specFields = meta.spec_fields.filter(
    (field) =>
      field.id !== 'location' &&
      (chosen.length === 0 || field.categories.some((c) => chosen.includes(c))),
  )

  function setClause(index: number, changes: Partial<SpecClause>) {
    const specs = [...(criteria.specs ?? [])]
    specs[index] = { ...specs[index], ...changes }
    patch({ specs })
  }

  function addClause() {
    const first = specFields[0]
    if (!first) return
    patch({
      specs: [
        ...(criteria.specs ?? []),
        { field: first.id, op: 'lte', value: '', unknown: 'exclude' },
      ],
    })
  }

  const enabledChannels = meta.channels.filter((c) => c.enabled)

  return (
    <form
      className="alert-builder"
      onSubmit={(e) => {
        e.preventDefault()
        onSave({
          id: initial?.id,
          name,
          criteria: normalize(criteria),
          channels,
          digest,
          max_per_day: maxPerDay,
          // stamp the viewer's zone so "quiet until 8am" means their 8am
          quiet_hours:
            quietFrom && quietTo
              ? {
                  tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
                  from: quietFrom,
                  to: quietTo,
                }
              : {},
        })
      }}
    >
      <label className="field">
        <span>Name this alert</span>
        <input
          className="input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="ATL subject-to under 8%"
          required
        />
      </label>

      <fieldset className="sheet-block">
        <legend className="eyebrow">Which deals</legend>
        <Pills
          options={meta.categories}
          selected={criteria.categories ?? []}
          onToggle={(v) => toggle('categories', v)}
        />
        <p className="faint">Pick none to watch every category.</p>
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">Where</legend>
        <Pills
          options={meta.cities}
          selected={criteria.cities ?? []}
          onToggle={(v) => toggle('cities', v)}
        />
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">HOA</legend>
        <Pills
          options={meta.hoa_states.map((s) => s.id)}
          selected={criteria.hoa ?? []}
          onToggle={(v) => toggle('hoa', v)}
          labelFor={(id) => meta.hoa_states.find((s) => s.id === id)?.label ?? id}
        />
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">The numbers</legend>
        {(criteria.specs ?? []).length > 0 && (
          <div className="schedule">
            <div className="schedule-head">
              <span>Field</span>
              <span>Condition</span>
              <span>Value</span>
              <span>If the post doesn't say</span>
              <span />
            </div>
            {(criteria.specs ?? []).map((clause, index) => {
              const field = meta.spec_fields.find((f) => f.id === clause.field)
              return (
                <div className="schedule-row" key={index}>
                  <select
                    className="select"
                    value={clause.field}
                    onChange={(e) => setClause(index, { field: e.target.value })}
                    aria-label="Spec field"
                  >
                    {specFields.map((f) => (
                      <option key={f.id} value={f.id}>
                        {fieldLabel(f.id)}
                      </option>
                    ))}
                  </select>
                  <select
                    className="select"
                    value={clause.op}
                    onChange={(e) => setClause(index, { op: e.target.value as SpecOp })}
                    aria-label="Condition"
                  >
                    {OPS.map((op) => (
                      <option key={op.id} value={op.id}>
                        {op.label}
                      </option>
                    ))}
                  </select>
                  {clause.op === 'between' ? (
                    <span className="between-pair">
                      <input
                        className="input"
                        value={Array.isArray(clause.value) ? String(clause.value[0] ?? '') : ''}
                        onChange={(e) =>
                          setClause(index, {
                            value: [
                              e.target.value,
                              Array.isArray(clause.value) ? clause.value[1] ?? '' : '',
                            ],
                          })
                        }
                        aria-label="Low value"
                      />
                      <input
                        className="input"
                        value={Array.isArray(clause.value) ? String(clause.value[1] ?? '') : ''}
                        onChange={(e) =>
                          setClause(index, {
                            value: [
                              Array.isArray(clause.value) ? clause.value[0] ?? '' : '',
                              e.target.value,
                            ],
                          })
                        }
                        aria-label="High value"
                      />
                    </span>
                  ) : field?.kind === 'enum' && field.options.length ? (
                    <select
                      className="select"
                      value={String(clause.value ?? '')}
                      onChange={(e) => setClause(index, { value: e.target.value })}
                      aria-label="Value"
                    >
                      <option value="">Choose…</option>
                      {field.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      className="input"
                      value={Array.isArray(clause.value) ? '' : String(clause.value ?? '')}
                      onChange={(e) => setClause(index, { value: e.target.value })}
                      aria-label="Value"
                    />
                  )}
                  <select
                    className="select"
                    value={clause.unknown}
                    onChange={(e) =>
                      setClause(index, { unknown: e.target.value as 'include' | 'exclude' })
                    }
                    aria-label="What to do when the value is unknown"
                  >
                    <option value="exclude">Skip the lead</option>
                    <option value="include">Send it anyway</option>
                  </select>
                  <button
                    type="button"
                    className="link-btn link-danger"
                    onClick={() =>
                      patch({ specs: (criteria.specs ?? []).filter((_, i) => i !== index) })
                    }
                    aria-label="Remove this condition"
                  >
                    Remove
                  </button>
                </div>
              )
            })}
          </div>
        )}
        <div>
          <button
            type="button"
            className="btn btn-sm"
            onClick={addClause}
            disabled={!specFields.length}
          >
            Add a condition
          </button>
        </div>
        <p className="faint">
          Most posts leave some numbers out. The last column decides what happens then.
        </p>
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">Gaps</legend>
        <Pills
          options={specFields.map((f) => f.id)}
          selected={criteria.unknowns_required ?? []}
          onToggle={(v) => toggle('unknowns_required', v)}
          labelFor={fieldLabel}
        />
        <p className="faint">
          Tell me when these are <em>still missing</em> — useful if your edge is being first to
          ask.
        </p>
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">Words</legend>
        <div className="word-row">
          <label className="field">
            <span>Must mention</span>
            <input
              className="input"
              value={(criteria.keywords_any ?? []).join(', ')}
              onChange={(e) =>
                patch({ keywords_any: splitWords(e.target.value) })
              }
              placeholder="tenant occupied, owner finance"
            />
          </label>
          <label className="field">
            <span>Never mention</span>
            <input
              className="input"
              value={(criteria.keywords_none ?? []).join(', ')}
              onChange={(e) => patch({ keywords_none: splitWords(e.target.value) })}
              placeholder="agent, realtor"
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="sheet-block">
        <legend className="eyebrow">How to reach you</legend>
        {enabledChannels.length === 0 ? (
          <p className="muted">
            No delivery channel is switched on yet. Ask the operator to configure one.
          </p>
        ) : (
          <div className="channel-list">
            {enabledChannels.map((channel: Channel) => (
              <label key={channel.id} className="channel">
                <input
                  type="checkbox"
                  checked={channels.includes(channel.id)}
                  onChange={() =>
                    setChannels((prev) =>
                      prev.includes(channel.id)
                        ? prev.filter((c) => c !== channel.id)
                        : [...prev, channel.id],
                    )
                  }
                />
                <span>
                  <strong>{channel.label}</strong>
                  <span className="faint channel-note">{channel.note}</span>
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="cadence-row">
          <label className="field">
            <span>How often</span>
            <select
              className="select"
              value={digest}
              onChange={(e) => setDigest(e.target.value as Alert['digest'])}
            >
              {DIGESTS.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Most per day</span>
            <input
              className="input"
              type="number"
              min={1}
              max={200}
              value={maxPerDay}
              onChange={(e) => setMaxPerDay(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>Quiet from</span>
            <input
              className="input"
              type="time"
              value={quietFrom}
              onChange={(e) => setQuietFrom(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Quiet until</span>
            <input
              className="input"
              type="time"
              value={quietTo}
              onChange={(e) => setQuietTo(e.target.value)}
            />
          </label>
        </div>
        <p className="faint">Anything that lands in quiet hours waits — it isn't dropped.</p>
      </fieldset>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="builder-actions">
        <button
          type="button"
          className="btn"
          onClick={() => preview.mutate(normalize(criteria))}
          disabled={preview.isPending}
        >
          {preview.isPending ? 'Checking…' : 'Show what this matches'}
        </button>
        <span className="lead-row-spacer" />
        <button type="button" className="btn btn-quiet" onClick={onCancel}>
          Cancel
        </button>
        <button className="btn btn-brass" disabled={saving || !name || !channels.length}>
          {saving ? 'Saving…' : initial ? 'Save changes' : 'Create alert'}
        </button>
      </div>

      {preview.data && (
        <div className="preview-result">
          <p>
            <strong className="num">{preview.data.total}</strong> of the posts on the board right
            now would have matched.
          </p>
          {preview.data.items.slice(0, 4).map((lead) => (
            <p key={lead.id} className="faint preview-line">
              {lead.category} · {lead.cities.join(', ') || 'no city named'} — {lead.snippet.slice(0, 90)}…
            </p>
          ))}
          {preview.data.total === 0 && (
            <p className="faint">
              Nothing yet. That's fine for a narrow alert — it just means you'll hear from it
              rarely.
            </p>
          )}
        </div>
      )}
    </form>
  )
}

function splitWords(raw: string): string[] {
  return raw
    .split(',')
    .map((word) => word.trim())
    .filter(Boolean)
}

/** Numbers arrive from the inputs as strings; the API compares numerically,
 *  so coerce here rather than making the server guess. */
function normalize(criteria: Criteria): Criteria {
  const specs = (criteria.specs ?? [])
    .filter((clause) =>
      Array.isArray(clause.value)
        ? clause.value.every((v) => String(v).trim() !== '')
        : String(clause.value ?? '').trim() !== '',
    )
    .map((clause) => ({
      ...clause,
      value: Array.isArray(clause.value)
        ? (clause.value.map(toNumberish) as (string | number)[])
        : toNumberish(clause.value),
    }))
  return { ...criteria, specs }
}

function toNumberish(value: string | number): string | number {
  if (typeof value === 'number') return value
  const cleaned = value.replace(/[$,%\s]/g, '')
  const asNumber = Number(cleaned)
  return cleaned !== '' && !Number.isNaN(asNumber) ? asNumber : value
}

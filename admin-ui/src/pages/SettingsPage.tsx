import { useState } from 'react'

import { usePurge } from '../api/hooks'
import type { PurgeResult } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { fmtDate } from '../lib/format'

interface Preset {
  label: string
  months?: number
  days?: number
}

/** "Older than" windows. 30 days is here because the monthly sweep's TTLs
 * keep most categories well under three months. */
const PRESETS: Preset[] = [
  { label: '30 days', days: 30 },
  { label: '3 months', months: 3 },
  { label: '6 months', months: 6 },
  { label: '12 months', months: 12 },
]

export function presetCutoff(preset: Preset, now = new Date()): string {
  const d = new Date(now)
  if (preset.months) d.setMonth(d.getMonth() - preset.months)
  if (preset.days) d.setDate(d.getDate() - preset.days)
  return d.toISOString().slice(0, 10)
}

function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
}

export function SettingsPage() {
  const purge = usePurge()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [active, setActive] = useState<string | null>(null)
  const [includeWorked, setIncludeWorked] = useState(false)
  const [preview, setPreview] = useState<PurgeResult | null>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState<PurgeResult | null>(null)

  function runPreview(fromDate: string, toDate: string) {
    setDone(null)
    purge.mutate(
      { from: fromDate, to: toDate, include_worked: includeWorked, dry_run: true },
      {
        onSuccess: (result) => {
          setPreview(result)
          setChecked(Object.fromEntries(Object.keys(result.by_category).map((c) => [c, true])))
          // show the real start of the window we just previewed, so both date
          // boxes are filled and re-running Preview reproduces this result
          if (result.matched_span.oldest) setFrom(result.matched_span.oldest.slice(0, 10))
        },
      },
    )
  }

  function quick(preset: Preset) {
    const cutoff = presetCutoff(preset)
    setActive(preset.label)
    setFrom('')
    setTo(cutoff)
    runPreview('', cutoff)
  }

  function manual(next: { from?: string; to?: string }) {
    setActive(null)
    if (next.from !== undefined) setFrom(next.from)
    if (next.to !== undefined) setTo(next.to)
  }

  const selectedCategories = Object.keys(checked).filter((c) => checked[c])
  const selectedCount = preview
    ? selectedCategories.reduce((sum, c) => sum + (preview.by_category[c] ?? 0), 0)
    : 0

  function executePurge() {
    purge.mutate(
      { from, to, include_worked: includeWorked, dry_run: false, categories: selectedCategories },
      {
        onSuccess: (result) => {
          setDone(result)
          setPreview(null)
          setConfirming(false)
        },
        onError: () => setConfirming(false),
      },
    )
  }

  return (
    <div className="settings-page">
      <h1 className="settings-title">Settings</h1>

      <section className="settings-card">
        <p className="eyebrow">Data management — purge old leads</p>
        <p className="muted">
          Deletes leads received in the selected window, including their notes. Two protections
          always apply: leads pinned with <strong>Keep</strong> are never purged, and leads with
          notes or follow-ups are skipped unless you include them below.
        </p>

        <div className="purge-quick">
          <span className="muted">Older than:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              className={active === preset.label ? 'btn btn-active' : 'btn'}
              disabled={purge.isPending}
              onClick={() => quick(preset)}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <div className="purge-range">
          <label>From
            <input
              className="input"
              type="date"
              value={from}
              onChange={(e) => manual({ from: e.target.value })}
            />
          </label>
          <label>To (required)
            <input
              className="input"
              type="date"
              value={to}
              onChange={(e) => manual({ to: e.target.value })}
            />
          </label>
          <label className="purge-check">
            <input
              type="checkbox"
              checked={includeWorked}
              onChange={(e) => setIncludeWorked(e.target.checked)}
            />
            Also purge leads that have notes/follow-ups
          </label>
          <button
            className="btn"
            disabled={!to || purge.isPending}
            onClick={() => runPreview(from, to)}
          >
            {purge.isPending ? 'Counting…' : 'Preview'}
          </button>
        </div>

        {purge.isError && <div className="error-banner">{(purge.error as Error).message}</div>}

        {preview && preview.would_purge === 0 && (
          <div className="purge-preview">
            <p>
              <strong>No leads</strong> fall in this window
              {preview.data_span.oldest && (
                <> — your oldest lead is from {fmtDate(preview.data_span.oldest)} (
                {daysSince(preview.data_span.oldest)} days old)</>
              )}
              .
            </p>
            {(preview.skipped_keep > 0 || preview.skipped_activity > 0) && (
              <p className="muted">
                {preview.skipped_keep} pinned · {preview.skipped_activity} with activity were protected.
              </p>
            )}
          </div>
        )}

        {preview && preview.would_purge > 0 && (
          <div className="purge-preview">
            <p>
              <strong>{preview.would_purge}</strong> lead{preview.would_purge === 1 ? '' : 's'} match
              {preview.would_purge === 1 ? 'es' : ''} ({fmtDate(preview.matched_span.oldest)} –{' '}
              {fmtDate(preview.matched_span.newest)}) · {preview.skipped_keep} kept (pinned) ·{' '}
              {preview.skipped_activity} skipped (have activity)
            </p>
            <p className="muted">Untick a category to leave it alone:</p>
            <div className="purge-cats">
              {Object.entries(preview.by_category).map(([c, n]) => (
                <label key={c} className="purge-cat">
                  <input
                    type="checkbox"
                    checked={checked[c] ?? false}
                    onChange={(e) => setChecked((prev) => ({ ...prev, [c]: e.target.checked }))}
                  />
                  {c} <span className="muted num">{n}</span>
                </label>
              ))}
            </div>
            <button
              className="btn btn-danger"
              disabled={selectedCount === 0 || purge.isPending}
              onClick={() => setConfirming(true)}
            >
              Purge {selectedCount} lead{selectedCount === 1 ? '' : 's'}…
            </button>
          </div>
        )}

        {done && (
          <p className="purge-done">
            ✓ Purged {done.purged} lead{done.purged === 1 ? '' : 's'} ({done.skipped_keep} pinned and{' '}
            {done.skipped_activity} active leads preserved).
          </p>
        )}
      </section>

      {confirming && preview && (
        <ConfirmDialog
          title={`Purge ${selectedCount} lead${selectedCount === 1 ? '' : 's'}?`}
          message={`This permanently deletes ${selectedCount} lead${selectedCount === 1 ? '' : 's'} in ${selectedCategories.length} categor${selectedCategories.length === 1 ? 'y' : 'ies'}, along with their notes. Pinned and active leads are preserved. This cannot be undone.`}
          confirmLabel="Purge"
          busy={purge.isPending}
          onCancel={() => setConfirming(false)}
          onConfirm={executePurge}
        />
      )}
    </div>
  )
}

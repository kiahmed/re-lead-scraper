import { useState } from 'react'

import { usePurge } from '../api/hooks'
import type { PurgeResult } from '../api/types'
import { ConfirmDialog } from '../components/ConfirmDialog'

function monthsAgo(n: number): string {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return d.toISOString().slice(0, 10)
}

export function SettingsPage() {
  const purge = usePurge()
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [includeWorked, setIncludeWorked] = useState(false)
  const [preview, setPreview] = useState<PurgeResult | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState<PurgeResult | null>(null)

  function runPreview(toDate = to, fromDate = from) {
    setDone(null)
    purge.mutate(
      { from: fromDate, to: toDate, include_worked: includeWorked, dry_run: true },
      { onSuccess: setPreview },
    )
  }

  function quick(n: number) {
    const cutoff = monthsAgo(n)
    setFrom('')
    setTo(cutoff)
    runPreview(cutoff, '')
  }

  function executePurge() {
    purge.mutate(
      { from, to, include_worked: includeWorked, dry_run: false },
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
          {[3, 6, 12].map((n) => (
            <button key={n} className="btn" onClick={() => quick(n)}>{n} months</button>
          ))}
        </div>

        <div className="purge-range">
          <label>From
            <input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label>To (required)
            <input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          <label className="purge-check">
            <input
              type="checkbox"
              checked={includeWorked}
              onChange={(e) => setIncludeWorked(e.target.checked)}
            />
            Also purge leads that have notes/follow-ups
          </label>
          <button className="btn" disabled={!to || purge.isPending} onClick={() => runPreview()}>
            {purge.isPending ? 'Counting…' : 'Preview'}
          </button>
        </div>

        {purge.isError && (
          <div className="error-banner">{(purge.error as Error).message}</div>
        )}

        {preview && (
          <div className="purge-preview">
            <p>
              <strong>{preview.would_purge}</strong> lead{preview.would_purge === 1 ? '' : 's'} would be
              permanently deleted · {preview.skipped_keep} kept (pinned) · {preview.skipped_activity} skipped
              (have activity)
            </p>
            {Object.keys(preview.by_category).length > 0 && (
              <p className="muted">
                {Object.entries(preview.by_category).map(([c, n]) => `${c}: ${n}`).join(' · ')}
              </p>
            )}
            <button
              className="btn btn-danger"
              disabled={preview.would_purge === 0 || purge.isPending}
              onClick={() => setConfirming(true)}
            >
              Purge {preview.would_purge} lead{preview.would_purge === 1 ? '' : 's'}…
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
          title={`Purge ${preview.would_purge} leads?`}
          message="This permanently deletes these leads and their notes from storage. Pinned and active leads are preserved. This cannot be undone."
          confirmLabel="Purge"
          busy={purge.isPending}
          onCancel={() => setConfirming(false)}
          onConfirm={executePurge}
        />
      )}
    </div>
  )
}

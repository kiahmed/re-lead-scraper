import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useSaveWorkspace, useWorkspace } from '../api/hooks'
import type { WorkStatus } from '../api/types'
import { NoteIcon, PinIcon } from '../components/Icons'
import { absoluteTime } from '../lib/format'

const TABS: { id: WorkStatus | 'all' | 'notes'; label: string }[] = [
  { id: 'all', label: 'Everything' },
  { id: 'working', label: 'Working' },
  { id: 'watching', label: 'Watching' },
  { id: 'passed', label: 'Passed' },
  { id: 'notes', label: 'What I wrote' },
]

export function WorkspacePage() {
  const workspace = useWorkspace()
  const save = useSaveWorkspace()
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>('all')

  const entries = workspace.data?.items ?? []
  const noteCounts = workspace.data?.note_counts ?? {}
  const notes = workspace.data?.notes ?? []

  const shown = useMemo(() => {
    if (tab === 'all' || tab === 'notes') return entries
    return entries.filter((e) => e.status === tab)
  }, [entries, tab])

  return (
    <div className="board">
      <div className="board-controls">
        <div>
          <h1 className="title-block page-title">Your workspace</h1>
          <p className="muted">
            Everything you pinned, worked, or wrote on — private to your account.
          </p>
        </div>
        <nav className="facet-rail" aria-label="Filter your workspace">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              className={`facet${tab === id ? ' facet-on' : ''}`}
              onClick={() => setTab(id)}
            >
              {label}{' '}
              <span className="num">
                {id === 'all'
                  ? entries.length
                  : id === 'notes'
                    ? notes.length
                    : entries.filter((e) => e.status === id).length}
              </span>
            </button>
          ))}
        </nav>
      </div>

      <div className="board-body">
        {workspace.isPending && <p className="muted board-msg">Opening your workspace…</p>}

        {tab === 'notes' ? (
          notes.length === 0 ? (
            <div className="empty-state">
              <p className="title-block">You haven't written anything yet</p>
              <p className="muted">
                Open a lead and jot down what the seller told you — it stays with the post.
              </p>
              <Link className="btn btn-brass" to="/browse">
                Go to the board
              </Link>
            </div>
          ) : (
            notes.map((note) => (
              <article key={note.id} className="lead-row">
                <p className="note-body">{note.body}</p>
                <div className="lead-row-foot faint">
                  <time dateTime={note.created_at}>{absoluteTime(note.created_at)}</time>
                  {note.edited && <span>· edited</span>}
                  <span className="lead-row-spacer" />
                  <Link to={`/leads/${encodeURIComponent(note.lead_id)}`}>Open the lead</Link>
                </div>
              </article>
            ))
          )
        ) : shown.length === 0 ? (
          <div className="empty-state">
            <p className="title-block">Nothing here yet</p>
            <p className="muted">
              Pin a lead from the board and it lands here, with whatever state you put it in.
            </p>
            <Link className="btn btn-brass" to="/browse">
              Go to the board
            </Link>
          </div>
        ) : (
          shown.map((entry) => (
            <article key={entry.lead_id} className="lead-row">
              <div className="lead-row-head">
                <span className={`chip status-${entry.status}`}>{entry.status}</span>
                {entry.tags.map((tag) => (
                  <span key={tag} className="chip chip-tag">
                    {tag}
                  </span>
                ))}
                <span className="lead-row-spacer" />
                {noteCounts[entry.lead_id] > 0 && (
                  <span className="note-count faint">
                    <NoteIcon /> {noteCounts[entry.lead_id]}
                  </span>
                )}
                <button
                  className={`icon-btn${entry.pinned ? ' icon-btn-on' : ''}`}
                  onClick={() => save.mutate({ leadId: entry.lead_id, pinned: !entry.pinned })}
                  aria-label={entry.pinned ? 'Unpin' : 'Pin'}
                >
                  <PinIcon filled={entry.pinned} />
                </button>
              </div>
              <div className="lead-row-foot faint">
                <time dateTime={entry.updated_at}>Updated {absoluteTime(entry.updated_at)}</time>
                <span className="lead-row-spacer" />
                <Link to={`/leads/${encodeURIComponent(entry.lead_id)}`}>Open the lead</Link>
              </div>
            </article>
          ))
        )}
      </div>
    </div>
  )
}

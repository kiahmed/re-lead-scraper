import { useState } from 'react'

import { useAddNote, useDeleteNote, useNotes, useUpdateNote } from '../../api/hooks'
import type { Note } from '../../api/types'
import { absoluteTime } from '../../lib/format'

function NoteCard({
  note,
  leadId,
  onDelete,
}: {
  note: Note
  leadId: string
  onDelete: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(note.body)
  const update = useUpdateNote(leadId)

  if (editing) {
    return (
      <div className="note-card">
        <textarea
          className="textarea"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="Edit your note"
        />
        <div className="note-actions">
          <button
            className="btn btn-sm"
            onClick={() => {
              setDraft(note.body)
              setEditing(false)
            }}
          >
            Cancel
          </button>
          <button
            className="btn btn-sm btn-primary"
            disabled={!draft.trim() || update.isPending}
            onClick={() =>
              update.mutate({ id: note.id, body: draft }, { onSuccess: () => setEditing(false) })
            }
          >
            Save note
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="note-card">
      <p className="note-body">{note.body}</p>
      <div className="note-meta faint">
        <time dateTime={note.created_at}>{absoluteTime(note.created_at)}</time>
        {note.edited && <span>· edited</span>}
        <span className="lead-row-spacer" />
        <button className="link-btn" onClick={() => setEditing(true)}>
          Edit
        </button>
        <button className="link-btn link-danger" onClick={() => onDelete(note.id)}>
          Delete
        </button>
      </div>
    </div>
  )
}

/** Notes are the one thing a public user can write here. They're private to
 *  the author — nothing on this pane is visible to anyone else. */
export function NotesPane({ leadId }: { leadId: string }) {
  const notes = useNotes(leadId)
  const add = useAddNote(leadId)
  const remove = useDeleteNote(leadId)
  const [draft, setDraft] = useState('')

  return (
    <section className="notes-pane">
      <div className="pane-head">
        <h2 className="eyebrow">Your notes</h2>
        <span className="faint">Private to you</span>
      </div>

      <form
        className="note-composer"
        onSubmit={(e) => {
          e.preventDefault()
          if (!draft.trim()) return
          add.mutate(draft, { onSuccess: () => setDraft('') })
        }}
      >
        <textarea
          className="textarea"
          placeholder="What did you find out? Who did you call?"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="Write a note"
        />
        <button className="btn btn-brass" disabled={!draft.trim() || add.isPending}>
          {add.isPending ? 'Saving…' : 'Add note'}
        </button>
      </form>

      {notes.data?.items.length === 0 && (
        <p className="muted note-empty">
          Nothing here yet. Your first note is a good place to park the seller's answer.
        </p>
      )}
      {notes.data?.items.map((note) => (
        <NoteCard key={note.id} note={note} leadId={leadId} onDelete={(id) => remove.mutate(id)} />
      ))}
    </section>
  )
}

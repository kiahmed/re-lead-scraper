import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { useDeleteLead, useLead, usePatchLead } from '../api/hooks'
import { CategoryChip } from '../components/CategoryChip'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { PencilIcon, TrashIcon } from '../components/Icons'
import { StatusGlyph } from '../components/StatusGlyph'
import { ActivityPane } from './panes/ActivityPane'
import { DealPane } from './panes/DealPane'
import { LeadEditForm } from './panes/LeadEditForm'

export function LeadDetailPage() {
  const { leadId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const editing = searchParams.get('edit') === '1'
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const { data: lead, isLoading, isError, error } = useLead(leadId)
  const deleteLead = useDeleteLead()
  const patchLead = usePatchLead(leadId)
  const navigate = useNavigate()

  if (isLoading) return <div className="screen-center muted">Loading lead…</div>
  if (isError || !lead) {
    return (
      <div className="screen-center">
        <div className="error-banner">
          {isError ? `Failed to load lead: ${(error as Error).message}` : 'Lead not found'}
        </div>
        <Link to="/">‹ Back to list</Link>
      </div>
    )
  }

  function setEditing(on: boolean) {
    setSearchParams(on ? { edit: '1' } : {}, { replace: true })
  }

  return (
    <div className="detail-page">
      <div className="detail-topbar">
        <Link to="/" className="back-link">‹ Back to list</Link>
        <strong>{lead.authorName || 'Unknown author'}</strong>
        <span className="muted">· {lead.groupName}</span>
        <CategoryChip category={lead.category} />
        <StatusGlyph {...lead} withLabel />
        <span className="row-actions detail-actions">
          <button
            className={lead.keep ? 'btn keep-btn keep-on' : 'btn keep-btn'}
            title={lead.keep ? 'Pinned — protected from purge' : 'Pin to protect from purge'}
            onClick={() => patchLead.mutate({ keep: !lead.keep })}
            disabled={patchLead.isPending}
          >
            {lead.keep ? '★ Kept' : '☆ Keep'}
          </button>
          {!editing && (
            <button className="icon-btn" aria-label="Edit lead" title="Edit" onClick={() => setEditing(true)}>
              <PencilIcon />
            </button>
          )}
          <button
            className="icon-btn icon-btn-danger"
            aria-label="Delete lead"
            title="Delete"
            onClick={() => setConfirmingDelete(true)}
          >
            <TrashIcon />
          </button>
        </span>
      </div>
      <div className="detail-panes">
        {editing
          ? <LeadEditForm lead={lead} onDone={() => setEditing(false)} />
          : <DealPane lead={lead} />}
        <ActivityPane lead={lead} />
      </div>
      {confirmingDelete && (
        <ConfirmDialog
          title="Delete lead?"
          message={`This permanently removes the lead from ${lead.authorName || 'unknown author'} and all its notes. This cannot be undone.`}
          busy={deleteLead.isPending}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() =>
            deleteLead.mutate(lead.id, { onSuccess: () => navigate('/', { replace: true }) })
          }
        />
      )}
    </div>
  )
}

import { Link, useParams } from 'react-router-dom'

import { useLead } from '../api/hooks'
import { CategoryChip } from '../components/CategoryChip'
import { StatusGlyph } from '../components/StatusGlyph'
import { ActivityPane } from './panes/ActivityPane'
import { DealPane } from './panes/DealPane'

export function LeadDetailPage() {
  const { leadId = '' } = useParams()
  const { data: lead, isLoading, isError, error } = useLead(leadId)

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

  return (
    <div className="detail-page">
      <div className="detail-topbar">
        <Link to="/" className="back-link">‹ Back to list</Link>
        <strong>{lead.authorName || 'Unknown author'}</strong>
        <span className="muted">· {lead.groupName}</span>
        <CategoryChip category={lead.category} />
        <StatusGlyph {...lead} withLabel />
      </div>
      <div className="detail-panes">
        <DealPane lead={lead} />
        <ActivityPane lead={lead} />
      </div>
    </div>
  )
}

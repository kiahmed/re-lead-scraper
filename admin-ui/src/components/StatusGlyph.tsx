import type { LeadSummary } from '../api/types'

/** ✓ complete · ⚠ incomplete · ⊘ skipped · ✕ error · ○ pending */
export function leadStatus(lead: Pick<LeadSummary, 'is_complete' | 'outreach_skipped' | 'errorMessage' | 'outreach_at'>) {
  if (lead.errorMessage && lead.errorMessage !== 'none') {
    return { glyph: '✕', label: 'Error', cls: 'status-err' }
  }
  if (lead.outreach_skipped) return { glyph: '⊘', label: 'Skipped', cls: 'status-muted' }
  if (!lead.outreach_at) return { glyph: '○', label: 'Pending', cls: 'status-muted' }
  if (lead.is_complete) return { glyph: '✓', label: 'Complete', cls: 'status-ok' }
  return { glyph: '⚠', label: 'Incomplete', cls: 'status-warn' }
}

export function StatusGlyph(props: Parameters<typeof leadStatus>[0] & { withLabel?: boolean }) {
  const s = leadStatus(props)
  return (
    <span className={`status ${s.cls}`} title={s.label}>
      {s.glyph}
      {props.withLabel ? ` ${s.label}` : ''}
    </span>
  )
}

export interface LeadSummary {
  id: string
  authorName: string
  groupName: string
  keywords: string[]
  category: string
  has_selling_intent: boolean | null
  is_complete: boolean | null
  outreach_skipped: boolean | null
  keep: boolean
  errorMessage: string
  missing_fields: string[]
  stored_at: string
  classified_at: string
  outreach_at: string
  snippet: string
}

export interface LeadDetail extends Omit<LeadSummary, 'snippet'> {
  url: string
  content: string
  contact: { author?: string; email?: string | null; phone?: string | null; dm_requested?: boolean }
  extracted_info: Record<string, unknown> | string
  outreach_message: string
  investment_summary: string
  location_insights: Record<string, string>
}

export interface LeadListResponse {
  items: LeadSummary[]
  total: number
  page: number
  pageSize: number
  counts: Record<string, number>
}

export interface Interaction {
  id: string
  type: 'note' | 'message_out' | 'follow_up' | 'status_change'
  body: string
  author: string
  channel: string
  status: string
  follow_up_at: string
  follow_up_done: boolean
  created_at: string
  updated_at: string
  edited: boolean
}

export interface User {
  username: string
  display_name: string
  role: string
  is_active: boolean
  last_login_at: string
}

export interface Meta {
  categories: string[]
  required_fields: Record<string, string[]>
  pipeline: { status: string; deployed_at: string; synced_at: string }
}

export interface DateSpan {
  oldest: string
  newest: string
}

export interface PurgeResult {
  dry_run: boolean
  matched: number
  purged: number
  would_purge: number
  skipped_keep: number
  skipped_activity: number
  skipped_undated: number
  matched_span: DateSpan
  data_span: DateSpan
  by_category: Record<string, number>
}

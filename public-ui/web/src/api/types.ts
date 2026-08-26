export type HoaState = 'none' | 'zero' | 'has'
export type SpecSource = 'stored' | 'parsed'

/** One recovered property spec. `source` is surfaced in the UI on purpose: a
 *  number read out of the post text is a weaker claim than one the pipeline
 *  recorded, and the reader deserves to know which they're looking at. */
export interface SpecValue {
  value: string | number
  source: SpecSource
  snippet: string
}

export interface LeadSummary {
  id: string
  authorName: string
  groupName: string
  keywords: string[]
  category: string
  has_selling_intent: boolean | null
  is_complete: boolean | null
  cities: string[]
  hoa: HoaState
  missing_fields: string[]
  specs: Record<string, SpecValue>
  stored_at: string
  classified_at: string
  outreach_at: string
  snippet: string
}

export interface LeadDetail extends Omit<LeadSummary, 'snippet'> {
  url: string
  content: string
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
  city_counts: Record<string, number>
  hoa_counts: Record<string, number>
}

export interface Note {
  id: string
  lead_id: string
  body: string
  created_at: string
  updated_at: string
  edited: boolean
}

export type WorkStatus = 'new' | 'watching' | 'working' | 'passed'

export interface SavedEntry {
  lead_id: string
  pinned: boolean
  status: WorkStatus
  tags: string[]
  created_at: string
  updated_at: string
}

export interface WorkspaceResponse {
  items: SavedEntry[]
  note_counts: Record<string, number>
  notes: Note[]
}

export interface User {
  email: string
  display_name: string
  email_verified: boolean
  phone: string
  phone_verified: boolean
  providers: { provider: string; sub: string }[]
  has_password: boolean
  tz: string
  created_at: string
  last_login_at: string
}

export interface Channel {
  id: 'email' | 'webpush' | 'sms'
  label: string
  enabled: boolean
  note: string
}

export interface SpecField {
  id: string
  kind: 'money' | 'percent' | 'months' | 'enum' | 'text'
  options: string[]
  categories: string[]
}

export interface Meta {
  categories: string[]
  cities: string[]
  hoa_states: { id: HoaState; label: string }[]
  required_fields: Record<string, string[]>
  spec_fields: SpecField[]
  channels: Channel[]
  oauth_providers: { id: string; label: string }[]
  pipeline: { status: string; deployed_at: string }
}

export type SpecOp = 'eq' | 'ne' | 'lt' | 'lte' | 'gt' | 'gte' | 'between' | 'contains'

export interface SpecClause {
  field: string
  op: SpecOp
  value: string | number | (string | number)[]
  unknown: 'include' | 'exclude'
}

export interface Criteria {
  categories?: string[]
  cities?: string[]
  hoa?: HoaState[]
  completeness?: 'any' | 'complete' | 'incomplete'
  keywords_any?: string[]
  keywords_none?: string[]
  specs?: SpecClause[]
  unknowns_required?: string[]
  unknowns_forbidden?: string[]
}

export interface Alert {
  id: string
  name: string
  criteria: Criteria
  channels: string[]
  digest: 'instant' | 'hourly' | 'daily'
  quiet_hours: { tz?: string; from?: string; to?: string }
  max_per_day: number
  enabled: boolean
  last_cursor: string
  last_fired_at: string
  sent_today: number
  created_at: string
  updated_at: string
}

export interface PreviewResult {
  total: number
  items: LeadSummary[]
  sample_window: { oldest: string; newest: string }
}

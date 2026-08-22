export function fmtDateTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function fmtDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** snake_case / camelCase → Title Case */
export function humanizeKey(key: string): string {
  return key
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function fmtValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') {
    if (Number.isInteger(value) && Math.abs(value) >= 1000) return value.toLocaleString()
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.map(fmtValue).join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/** Format a bare yyyy-mm-dd date-input value. Parsed as local parts, not
 * via Date(string), which treats it as UTC and can shift the day. */
export function fmtDateOnly(ymd: string): string {
  if (!ymd) return '—'
  const [y, m, d] = ymd.split('-').map(Number)
  if (!y || !m || !d) return ymd
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

/** Facebook post URL: stored url when present, else derived from the lead id
 * (base64 "S:_I<authorId>:VK:<postId>" → story.php permalink). */
export function postUrl(lead: { url?: string; id: string }): string {
  if (lead.url) return lead.url
  const m = lead.id.match(/^facebook_(.+)$/)
  if (!m) return ''
  try {
    const decoded = atob(m[1])
    const parts = decoded.match(/^S:_I(\d+):VK:(\d+)$/)
    if (!parts) return ''
    return `https://www.facebook.com/story.php?story_fbid=${parts[2]}&id=${parts[1]}`
  } catch {
    return ''
  }
}

const CATEGORY_CLASS: Record<string, string> = {
  'Subject-To': 'subject-to',
  'Seller Finance': 'seller-finance',
  'Hybrid': 'hybrid',
  'Fix & Flip': 'fix-flip',
  'JV or Wholesale': 'jv-wholesale',
  'Buyers Looking': 'buyers-looking',
  'Regular': 'regular',
  'Others': 'others',
}

export function categoryClass(category: string): string {
  return CATEGORY_CLASS[category] ?? 'others'
}

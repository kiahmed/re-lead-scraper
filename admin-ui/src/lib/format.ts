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

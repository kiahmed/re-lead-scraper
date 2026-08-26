import type { SpecValue } from '../api/types'

const MONEY_FIELDS = new Set([
  'loan_balance',
  'monthly_payment',
  'asking_price',
  'down_payment',
  'seller_carry_amount',
  'ARV',
  'rehab_cost',
])

/** Field ids come from values.yaml, so they read like `loan_balance`. */
export function fieldLabel(field: string): string {
  if (field === 'ARV') return 'ARV'
  return field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatSpec(field: string, spec: SpecValue): string {
  const { value } = spec
  if (MONEY_FIELDS.has(field) && typeof value === 'number') {
    return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
  }
  if (field === 'interest_rate') return `${value}%`
  if (field === 'term' && typeof value === 'number') {
    return value % 12 === 0 ? `${value / 12} yr` : `${value} mo`
  }
  return String(value)
}

export function relativeTime(iso: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function absoluteTime(iso: string): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

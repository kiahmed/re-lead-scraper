import { describe, expect, it } from 'vitest'

import { fieldLabel, formatSpec, relativeTime } from './format'

describe('fieldLabel', () => {
  it('turns values.yaml field ids into readable labels', () => {
    expect(fieldLabel('loan_balance')).toBe('Loan Balance')
    expect(fieldLabel('occupancy_status')).toBe('Occupancy Status')
  })

  it('leaves acronyms alone', () => {
    expect(fieldLabel('ARV')).toBe('ARV')
  })
})

describe('formatSpec', () => {
  const spec = (value: string | number) => ({ value, source: 'parsed' as const, snippet: '' })

  it('renders money with separators and no cents', () => {
    expect(formatSpec('loan_balance', spec(185000))).toBe('$185,000')
    expect(formatSpec('ARV', spec(260000))).toBe('$260,000')
  })

  it('renders a rate as a percentage', () => {
    expect(formatSpec('interest_rate', spec(4.25))).toBe('4.25%')
  })

  it('shows a whole-year term in years, an odd one in months', () => {
    expect(formatSpec('term', spec(360))).toBe('30 yr')
    expect(formatSpec('term', spec(18))).toBe('18 mo')
  })

  it('passes text through untouched', () => {
    expect(formatSpec('occupancy_status', spec('tenant occupied'))).toBe('tenant occupied')
  })
})

describe('relativeTime', () => {
  it('handles empty and unparseable values without throwing', () => {
    expect(relativeTime('')).toBe('—')
    expect(relativeTime('not a date')).toBe('—')
  })

  it('counts back in the largest sensible unit', () => {
    const minutesAgo = new Date(Date.now() - 45 * 60_000).toISOString()
    expect(relativeTime(minutesAgo)).toBe('45m ago')
    const hoursAgo = new Date(Date.now() - 5 * 3_600_000).toISOString()
    expect(relativeTime(hoursAgo)).toBe('5h ago')
  })
})

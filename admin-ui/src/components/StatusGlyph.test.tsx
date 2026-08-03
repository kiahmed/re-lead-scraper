import { describe, expect, it } from 'vitest'

import { leadStatus } from './StatusGlyph'

const base = { is_complete: null, outreach_skipped: null, errorMessage: '', outreach_at: '' }

describe('leadStatus', () => {
  it('error wins over everything', () => {
    expect(leadStatus({ ...base, errorMessage: 'boom', outreach_at: 'x', is_complete: true }).label).toBe('Error')
  })
  it('"none" errorMessage is not an error', () => {
    expect(leadStatus({ ...base, errorMessage: 'none', outreach_at: 'x', is_complete: true }).label).toBe('Complete')
  })
  it('skipped, pending, complete, incomplete', () => {
    expect(leadStatus({ ...base, outreach_skipped: true }).label).toBe('Skipped')
    expect(leadStatus(base).label).toBe('Pending')
    expect(leadStatus({ ...base, outreach_at: 'x', is_complete: true }).label).toBe('Complete')
    expect(leadStatus({ ...base, outreach_at: 'x', is_complete: false }).label).toBe('Incomplete')
  })
})

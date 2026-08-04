import { describe, expect, it } from 'vitest'

import { categoryClass, fmtValue, humanizeKey, postUrl } from './format'

describe('humanizeKey', () => {
  it('converts snake_case and camelCase', () => {
    expect(humanizeKey('loan_balance')).toBe('Loan Balance')
    expect(humanizeKey('medianRentEstimate')).toBe('Median Rent Estimate')
  })
})

describe('fmtValue', () => {
  it('renders empties as em dash', () => {
    expect(fmtValue(null)).toBe('—')
    expect(fmtValue('')).toBe('—')
    expect(fmtValue(undefined)).toBe('—')
  })
  it('formats numbers, booleans, arrays, objects', () => {
    expect(fmtValue(210000)).toBe('210,000')
    expect(fmtValue(3.1)).toBe('3.1')
    expect(fmtValue(true)).toBe('Yes')
    expect(fmtValue(['a', 'b'])).toBe('a, b')
    expect(fmtValue({ x: 1 })).toBe('{"x":1}')
  })
})

describe('categoryClass', () => {
  it('maps known categories and falls back to others', () => {
    expect(categoryClass('Fix & Flip')).toBe('fix-flip')
    expect(categoryClass('JV or Wholesale')).toBe('jv-wholesale')
    expect(categoryClass('Weird New Category')).toBe('others')
  })
})

describe('postUrl', () => {
  it('prefers the stored url', () => {
    expect(postUrl({ id: 'facebook_x', url: 'https://fb.com/p/1' })).toBe('https://fb.com/p/1')
  })
  it('derives a story.php permalink from the encoded id', () => {
    const id = 'facebook_' + btoa('S:_I100000074247130:VK:1645182933436241')
    expect(postUrl({ id })).toBe(
      'https://www.facebook.com/story.php?story_fbid=1645182933436241&id=100000074247130',
    )
  })
  it('returns empty for underivable ids', () => {
    expect(postUrl({ id: 'facebook_!!!notbase64' })).toBe('')
    expect(postUrl({ id: 'zillow_123' })).toBe('')
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { SpecValue } from '../api/types'
import { SpecLedger } from './SpecLedger'

const lead = (specs: Record<string, SpecValue>) => ({ specs })

describe('SpecLedger', () => {
  it('shows a value the pipeline recorded without the parsed marker', () => {
    render(
      <SpecLedger
        lead={lead({ asking_price: { value: 195000, source: 'stored', snippet: '' } })}
        fields={['asking_price']}
      />,
    )
    const value = screen.getByText('$195,000')
    expect(value).toHaveClass('spec-stored')
    expect(value).toHaveAttribute('title', 'Recorded by the pipeline')
  })

  it('marks a value read out of the post and quotes the words it came from', () => {
    render(
      <SpecLedger
        lead={lead({
          interest_rate: { value: 4.25, source: 'parsed', snippet: 'at 4.25%' },
        })}
        fields={['interest_rate']}
      />,
    )
    const value = screen.getByText('4.25%')
    expect(value).toHaveClass('spec-parsed')
    expect(value).toHaveAttribute('title', 'Read from the post: “at 4.25%”')
  })

  it('renders a spec the post never stated as a ruled blank, not a zero', () => {
    render(
      <SpecLedger
        lead={lead({ asking_price: { value: 195000, source: 'parsed', snippet: 'asking 195k' } })}
        fields={['asking_price', 'loan_balance']}
      />,
    )
    expect(screen.getByText('Loan Balance')).toBeInTheDocument()
    expect(screen.getByText('not stated')).toBeInTheDocument()
    // critically: no fabricated number
    expect(screen.queryByText('$0')).not.toBeInTheDocument()
  })

  it('renders nothing when every value would be a blank', () => {
    // a row of pure blanks is empty space pretending to be data
    const { container } = render(
      <SpecLedger lead={lead({})} fields={['loan_balance', 'asking_price']} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('can hide blanks where space is tight', () => {
    const { container } = render(
      <SpecLedger lead={lead({})} fields={['loan_balance']} showBlanks={false} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})

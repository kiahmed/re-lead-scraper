import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ShareCluster } from './ShareCluster'
import { ToastProvider } from './Toast'

function setup(props = {}) {
  return render(
    <ToastProvider>
      <ShareCluster url="https://example.test/leads/1" {...props} />
    </ToastProvider>,
  )
}

describe('ShareCluster', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // @ts-expect-error navigator.share is optional in jsdom
    delete navigator.share
  })

  it('uses the native share sheet when the browser has one', async () => {
    const share = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { share })
    setup()
    await userEvent.click(screen.getByRole('button', { name: /share/i }))
    expect(share).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'https://example.test/leads/1' }),
    )
  })

  it('falls back to copying the link and says so', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    setup()
    await userEvent.click(screen.getByRole('button', { name: /share/i }))
    expect(writeText).toHaveBeenCalledWith('https://example.test/leads/1')
    expect(await screen.findByText('Link copied')).toBeInTheDocument()
  })

  it('stays quiet when the user dismisses the sheet', async () => {
    Object.assign(navigator, { share: vi.fn().mockRejectedValue(new Error('AbortError')) })
    setup()
    await userEvent.click(screen.getByRole('button', { name: /share/i }))
    expect(screen.queryByText('Link copied')).not.toBeInTheDocument()
  })

  it('links out to the social accounts, and hides them in compact mode', () => {
    const { rerender } = setup()
    expect(screen.getByRole('link', { name: /on X/i })).toHaveAttribute(
      'href',
      'https://x.com/flynestleads',
    )
    rerender(
      <ToastProvider>
        <ShareCluster compact />
      </ToastProvider>,
    )
    expect(screen.queryByRole('link', { name: /on X/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument()
  })
})

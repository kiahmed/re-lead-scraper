import { useState } from 'react'

export function Section({
  title,
  children,
  defaultOpen = true,
  aside,
}: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  aside?: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="detail-section">
      <header className="detail-section-header">
        <button className="section-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          <span className="eyebrow">{title}</span>
          <span className="muted">{open ? '⌄' : '›'}</span>
        </button>
        {aside}
      </header>
      {open && <div className="detail-section-body">{children}</div>}
    </section>
  )
}

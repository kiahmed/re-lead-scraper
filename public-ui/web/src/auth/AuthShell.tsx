import { Link } from 'react-router-dom'

import { PropertyFrieze } from '../components/PropertyFrieze'
import { ShareCluster } from '../components/ShareCluster'

/**
 * The front door. The frieze does the talking here — it's the one place the
 * drawing runs at full size, so the pitch is visual before it is verbal.
 */
export function AuthShell({
  eyebrow,
  heading,
  children,
}: {
  eyebrow: string
  heading: string
  children: React.ReactNode
}) {
  return (
    <div className="auth-page">
      <header className="auth-head">
        <Link to="/" className="wordmark">
          <span className="wordmark-rule" aria-hidden="true" />
          FlyNest
        </Link>
        <ShareCluster />
      </header>

      <section className="auth-hero">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="title-block auth-headline">{heading}</h1>
        <p className="auth-sub">
          Sellers post creative-finance deals in Facebook groups all day. We read every one,
          keep the ones that fit, and pull the numbers off the page so you can judge a deal in
          a glance instead of a scroll.
        </p>
        <div className="frieze-crop">
          <PropertyFrieze variant="hero" />
        </div>
      </section>

      <section className="auth-card-wrap">{children}</section>

      <footer className="auth-foot muted">
        <span>Notes and alerts are yours alone — nobody else on the board can see them.</span>
      </footer>
    </div>
  )
}

import { useMeta } from '../api/hooks'
import { FacebookLogo, GoogleLogo, MicrosoftLogo } from '../components/Icons'

const LOGOS: Record<string, () => React.ReactElement> = {
  google: GoogleLogo,
  microsoft: MicrosoftLogo,
  facebook: FacebookLogo,
}

/** Only providers the server says are configured get a button — a dead
 *  sign-in button is worse than no button. */
export function ProviderButtons({ next = '/browse' }: { next?: string }) {
  const meta = useMeta()
  const providers = meta.data?.oauth_providers ?? []
  if (!providers.length) return null

  return (
    <>
      <div className="provider-row">
        {providers.map(({ id, label }) => {
          const Logo = LOGOS[id]
          return (
            <a
              key={id}
              className="btn provider-btn"
              href={`/api/auth/oauth/${id}?next=${encodeURIComponent(next)}`}
            >
              {Logo && <Logo />}
              <span>Continue with {label}</span>
            </a>
          )
        })}
      </div>
      <div className="or-rule">
        <span>or</span>
      </div>
    </>
  )
}

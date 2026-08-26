import { FacebookLogo, LinkedInLogo, ShareIcon, XLogo } from './Icons'
import { useToast } from './Toast'

const SOCIALS = [
  { id: 'x', label: 'FlyNest on X', href: 'https://x.com/flynestleads', Logo: XLogo },
  {
    id: 'linkedin',
    label: 'FlyNest on LinkedIn',
    href: 'https://www.linkedin.com/company/flynest-leads',
    Logo: LinkedInLogo,
  },
  {
    id: 'facebook',
    label: 'FlyNest on Facebook',
    href: 'https://www.facebook.com/flynestleads',
    Logo: FacebookLogo,
  },
]

/**
 * Social chips plus a share control — the native share sheet where the
 * browser offers one, a clipboard copy everywhere else. Matches the cluster
 * on the sibling EdgeLane product so the two read as the same family.
 */
export function ShareCluster({
  title = 'FlyNest Deal Board',
  text = 'Creative-finance seller posts, filtered and measured.',
  url,
  compact = false,
}: {
  title?: string
  text?: string
  url?: string
  compact?: boolean
}) {
  const { toast } = useToast()
  const target = url ?? (typeof window !== 'undefined' ? window.location.href : '')

  async function share() {
    const payload = { title, text, url: target }
    try {
      if (navigator.share) {
        await navigator.share(payload)
        return
      }
      await navigator.clipboard.writeText(target)
      toast('Link copied')
    } catch {
      // the user dismissed the sheet, or the clipboard is blocked — either
      // way there is nothing useful to say
    }
  }

  return (
    <div className="share-cluster">
      {!compact &&
        SOCIALS.map(({ id, label, href, Logo }) => (
          <a
            key={id}
            className="social-chip"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={label}
          >
            <Logo />
          </a>
        ))}
      <button className="share-chip" onClick={share} aria-label={`Share ${title}`}>
        <ShareIcon />
        <span>Share</span>
      </button>
    </div>
  )
}

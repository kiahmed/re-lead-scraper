/** Single-weight line icons, drawn to match the frieze's stroke. */
const stroke = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

function Svg({ children, size = 16 }: { children: React.ReactNode; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <g {...stroke}>{children}</g>
    </svg>
  )
}

export const PinIcon = ({ filled = false }: { filled?: boolean }) => (
  <svg width={16} height={16} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <g {...stroke} fill={filled ? 'currentColor' : 'none'}>
      <path d="M9 3h6l-1 6 4 3v2H6v-2l4-3-1-6Z" />
      <path d="M12 14v7" fill="none" />
    </g>
  </svg>
)

export const NoteIcon = () => (
  <Svg>
    <path d="M5 4h14v16l-4-3H5V4Z" />
    <path d="M9 9h6M9 13h4" />
  </Svg>
)

export const ShareIcon = () => (
  <Svg size={15}>
    <circle cx="18" cy="5" r="2.6" />
    <circle cx="6" cy="12" r="2.6" />
    <circle cx="18" cy="19" r="2.6" />
    <path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4" />
  </Svg>
)

export const BellIcon = () => (
  <Svg>
    <path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 2 6H4c.5-.5 2-2 2-6Z" />
    <path d="M10 19a2 2 0 0 0 4 0" />
  </Svg>
)

export const SearchIcon = () => (
  <Svg size={15}>
    <circle cx="11" cy="11" r="6" />
    <path d="M15.5 15.5 20 20" />
  </Svg>
)

export const ExternalIcon = () => (
  <Svg size={14}>
    <path d="M14 4h6v6" />
    <path d="M20 4 11 13" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Svg>
)

export const CheckIcon = () => (
  <Svg size={14}>
    <path d="m5 12 4.5 4.5L19 7" />
  </Svg>
)

export const XIcon = () => (
  <Svg size={14}>
    <path d="m6 6 12 12M18 6 6 18" />
  </Svg>
)

export const PlusIcon = () => (
  <Svg size={14}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
)

/** Brand marks are solid, not stroked — they're logos, not drawings. */
export const XLogo = () => (
  <svg width={15} height={15} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24h-6.66l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231 5.45-6.231Zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77Z" />
  </svg>
)

export const LinkedInLogo = () => (
  <svg width={15} height={15} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.13 1.45-2.13 2.94v5.67H9.35V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14ZM7.12 20.45H3.55V9h3.57v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0Z" />
  </svg>
)

export const FacebookLogo = () => (
  <svg width={15} height={15} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.09 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.09 24 18.1 24 12.07Z" />
  </svg>
)

export const GoogleLogo = () => (
  <svg width={16} height={16} viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M23.5 12.27c0-.79-.07-1.54-.2-2.27H12v4.51h6.47a5.54 5.54 0 0 1-2.4 3.64v3h3.86c2.26-2.08 3.57-5.15 3.57-8.88Z" />
    <path fill="#34A853" d="M12 24c3.24 0 5.96-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09A11.99 11.99 0 0 0 12 24Z" />
    <path fill="#FBBC05" d="M5.27 14.29a7.2 7.2 0 0 1 0-4.58V6.62H1.29a12 12 0 0 0 0 10.76l3.98-3.09Z" />
    <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.7 0 3.99 2.47 1.29 6.62l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75Z" />
  </svg>
)

export const MicrosoftLogo = () => (
  <svg width={16} height={16} viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#F25022" d="M1 1h10.2v10.2H1z" />
    <path fill="#7FBA00" d="M12.8 1H23v10.2H12.8z" />
    <path fill="#00A4EF" d="M1 12.8h10.2V23H1z" />
    <path fill="#FFB900" d="M12.8 12.8H23V23H12.8z" />
  </svg>
)

/**
 * The drafting frieze — this app's one loud idea.
 *
 * A single-weight site elevation: bungalow, duplex, framing under a crane, an
 * RV on its hookup, a staked vacant lot, a mid-rise, a stack of coins. Each
 * structure carries a drafting dimension line, and the label on that line is a
 * creative-finance term. The vocabulary measures the buildings rather than
 * floating over them as decoration — which is the whole pitch: we put numbers
 * on posts other people scroll past.
 *
 * `hero` draws itself in once on load; `strip` is a quiet ambient band for the
 * page header. Reduced motion renders it already drawn.
 */
type Variant = 'hero' | 'strip'

interface Dimension {
  from: number
  to: number
  y: number
  label: string
}

const DIMENSIONS: Dimension[] = [
  { from: 28, to: 162, y: 40, label: 'Subject-To' },
  { from: 170, to: 330, y: 36, label: 'Seller Carry' },
  { from: 350, to: 560, y: 22, label: 'ARV' },
  { from: 596, to: 770, y: 78, label: 'DSCR' },
  { from: 790, to: 955, y: 74, label: 'Balloon' },
  { from: 975, to: 1085, y: 30, label: 'Assumable' },
  { from: 1112, to: 1188, y: 34, label: 'PITI' },
]

/** Architectural slash ticks read as drafting; arrowheads read as clip art. */
function DimensionLine({ dim, index }: { dim: Dimension; index: number }) {
  const { from, to, y, label } = dim
  const tick = 5
  return (
    <g className="frieze-dim" style={{ '--i': index } as React.CSSProperties}>
      <line x1={from} y1={y} x2={to} y2={y} />
      <line x1={from} y1={y - tick} x2={from + tick} y2={y + tick} />
      <line x1={to - tick} y1={y - tick} x2={to} y2={y + tick} />
      <line x1={from} y1={y} x2={from} y2={y + 14} className="frieze-ext" />
      <line x1={to} y1={y} x2={to} y2={y + 14} className="frieze-ext" />
      <text x={(from + to) / 2} y={y - 9} textAnchor="middle">
        {label.toUpperCase()}
      </text>
    </g>
  )
}

export function PropertyFrieze({
  variant = 'hero',
  className = '',
}: {
  variant?: Variant
  className?: string
}) {
  const showLabels = variant === 'hero'
  return (
    <svg
      className={`frieze frieze-${variant} ${className}`}
      // The strip is a window onto y=104..152 — the building footings and the
      // ground line. Cropping to the drawing's *bottom* edge instead shows the
      // empty margin under the datum, which is what an earlier pass did.
      viewBox={showLabels ? '0 0 1200 210' : '0 104 1200 48'}
      preserveAspectRatio={showLabels ? 'xMidYMid meet' : 'xMidYMid slice'}
      role="img"
      aria-label="A drafting elevation of a bungalow, duplex, building under construction, RV, vacant lot, mid-rise and a stack of coins, dimensioned with creative-finance terms"
      focusable="false"
    >
      <g className="frieze-ink" fill="none" strokeLinecap="round" strokeLinejoin="round">
        {/* ground line — the datum everything sits on */}
        <line className="frieze-ground" x1={20} y1={150} x2={1190} y2={150} />

        {/* 1 — bungalow */}
        <g className="frieze-part" style={{ '--i': 0 } as React.CSSProperties}>
          <path d="M40 150 V100 H150 V150" />
          <path d="M28 100 L95 62 L162 100" />
          <path d="M82 150 V118 H104 V150" />
          <rect x={52} y={110} width={20} height={18} />
          <rect x={118} y={110} width={20} height={18} />
        </g>

        {/* 2 — duplex */}
        <g className="frieze-part" style={{ '--i': 1 } as React.CSSProperties}>
          <path d="M180 150 V92 H320 V150" />
          <path d="M170 92 L250 58 L330 92" />
          <path d="M250 150 V92" />
          <path d="M203 150 V120 H223 V150" />
          <path d="M277 150 V120 H297 V150" />
          <rect x={193} y={100} width={18} height={14} />
          <rect x={289} y={100} width={18} height={14} />
        </g>

        {/* 3 — framing under a crane */}
        <g className="frieze-part" style={{ '--i': 2 } as React.CSSProperties}>
          <path d="M350 150 V85 H480 V150" />
          <path d="M382 150 V85 M415 150 V85 M447 150 V85" />
          <path d="M350 118 H480" />
          <path d="M505 150 V40" />
          <path d="M505 150 L516 128 L505 106 L516 84 L505 62 L516 44" />
          <path d="M470 40 H560" />
          <path d="M545 40 V68" />
          <rect x={537} y={68} width={16} height={11} />
        </g>

        {/* 4 — RV on its hookup */}
        <g className="frieze-part" style={{ '--i': 3 } as React.CSSProperties}>
          <path d="M596 150 V116 Q596 108 606 108 H700 V150" />
          <circle cx={622} cy={150} r={8} />
          <circle cx={680} cy={150} r={8} />
          <rect x={612} y={117} width={24} height={15} />
          <path d="M652 150 V121 H670 V150" />
          <path d="M700 112 L744 100 M744 100 V134" />
          <path d="M762 150 V112" />
          <rect x={756} y={103} width={13} height={9} />
        </g>

        {/* 5 — staked vacant lot */}
        <g className="frieze-part" style={{ '--i': 4 } as React.CSSProperties}>
          <path d="M790 150 V132 M820 150 V132 M850 150 V132 M880 150 V132" />
          <path d="M790 138 H880" />
          <path d="M927 150 V118" />
          <rect x={899} y={96} width={56} height={24} />
          <path d="M909 108 H945" />
        </g>

        {/* 6 — mid-rise */}
        <g className="frieze-part" style={{ '--i': 5 } as React.CSSProperties}>
          <path d="M975 150 V52 H1085 V150" />
          <path d="M975 76 H1085 M975 100 H1085 M975 124 H1085" />
          <path d="M1002 52 V150 M1030 52 V150 M1058 52 V150" />
          <path d="M1014 150 V130 H1046 V150" />
        </g>

        {/* 7 — the money */}
        <g className="frieze-part" style={{ '--i': 6 } as React.CSSProperties}>
          <ellipse cx={1150} cy={144} rx={34} ry={8} />
          <ellipse cx={1150} cy={130} rx={34} ry={8} />
          <ellipse cx={1150} cy={116} rx={34} ry={8} />
          <path d="M1116 116 V144 M1184 116 V144" />
          <circle cx={1150} cy={78} r={18} />
          <path d="M1150 66 V90 M1144 72 H1156 M1144 84 H1156" />
        </g>
      </g>

      {showLabels && (
        <g className="frieze-dims">
          {DIMENSIONS.map((dim, i) => (
            <DimensionLine key={dim.label} dim={dim} index={i} />
          ))}
        </g>
      )}
    </svg>
  )
}

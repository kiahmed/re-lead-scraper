import type { SpecValue } from '../api/types'
import { fieldLabel, formatSpec } from '../lib/format'

/**
 * The deal numbers as a ledger strip.
 *
 * Two things this has to be honest about, because the pipeline stores no
 * structured specs and everything numeric here was recovered by us:
 *   • a value read out of the post text is underlined with a dotted rule and
 *     carries its matched snippet in the tooltip
 *   • a spec the post never stated renders as a ruled blank, the way an
 *     unfilled field looks on a paper form — which is also exactly what the
 *     alert builder's "if unknown" switch is about
 */
export function SpecLedger({
  lead,
  fields,
  showBlanks = true,
}: {
  // narrow on purpose — list rows and the detail page share this
  lead: { specs: Record<string, SpecValue> }
  fields: string[]
  showBlanks?: boolean
}) {
  const shown = fields.filter((field) => showBlanks || lead.specs[field])
  // a row of nothing but ruled blanks is just empty space — the "N unknown"
  // chip already says the post is thin
  if (!shown.length || !shown.some((field) => lead.specs[field])) return null

  return (
    <dl className="spec-ledger">
      {shown.map((field) => {
        const spec = lead.specs[field]
        return (
          <div key={field} className={`spec-cell${spec ? '' : ' spec-unknown'}`}>
            <dt>{fieldLabel(field)}</dt>
            {spec ? (
              <dd
                className={`num spec-${spec.source}`}
                title={
                  spec.source === 'parsed'
                    ? `Read from the post: “${spec.snippet}”`
                    : 'Recorded by the pipeline'
                }
              >
                {formatSpec(field, spec)}
              </dd>
            ) : (
              <dd className="spec-blank" title="The post doesn't say">
                <span className="visually-hidden">not stated</span>
              </dd>
            )}
          </div>
        )
      })}
    </dl>
  )
}

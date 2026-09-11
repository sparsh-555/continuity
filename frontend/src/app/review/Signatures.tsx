import { DEPARTMENT_ORDER, departmentLabel } from './Departments'

/** The desks that must sign, in the order every other screen renders them in.
 *
 * A desk this build has no place for keeps its position at the end rather than being
 * dropped: the row states how many signatures a change needs, and a row that silently
 * omitted one would understate what is outstanding.
 */
export function signingOrder(roles: readonly string[]): string[] {
  const known = DEPARTMENT_ORDER as readonly string[]
  const rank = (role: string) => {
    const at = known.indexOf(role)
    return at === -1 ? known.length : at
  }
  return [...roles].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
}

/** How many desks have signed of how many that must, and which are outstanding.
 *
 * In words rather than as a colour, for the same reason every other count in this product
 * is: it is read on a projector and in a screenshot, and *two of four* survives both.
 */
export function signatureSummary(
  roles: readonly string[],
  signed: readonly string[],
): string {
  const must = signingOrder(roles)
  const have = must.filter((role) => signed.includes(role))
  const outstanding = must.filter((role) => !signed.includes(role))
  if (outstanding.length === 0) return `${have.length} of ${must.length} signed.`
  return `${have.length} of ${must.length} signed. Waiting on ${outstanding
    .map(departmentLabel)
    .join(', ')
    .replace(/, ([^,]*)$/, ' and $1')}.`
}

/**
 * Every desk that must sign, ticked where it has.
 *
 * A substitution on a released design is signed by each desk that examined it, and until now
 * the only place that said *who* was a sentence on a queue: a reader could see that two
 * signatures were missing without seeing which two without reading a paragraph. The tick is
 * the same statement in the shape the eye already scans.
 *
 * The name is always printed beside the mark. A tick alone would make the row unreadable in
 * greyscale, and this product already states that rule for verdicts.
 */
export function SignatureRow({
  roles,
  signed,
  tone = 'text-[10px]',
}: {
  roles: readonly string[]
  signed: readonly string[]
  /** The row is set at three sizes across the page it appears on. One component rather than
   *  three, because a tick row that drifted between the queue and the document would be two
   *  answers to one question. */
  tone?: string
}) {
  if (roles.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-x-md gap-y-1">
      {signingOrder(roles).map((role) => {
        const has = signed.includes(role)
        return (
          <span className={`flex items-center gap-xs font-data-tabular ${tone}`} key={role}>
            <span
              aria-hidden
              className={`material-symbols-outlined text-[13px] ${
                has ? 'text-[#4ade80]' : 'text-on-surface-variant/50'
              }`}
              style={has ? { fontVariationSettings: "'FILL' 1" } : undefined}
            >
              {has ? 'check_circle' : 'radio_button_unchecked'}
            </span>
            <span className={has ? 'text-on-surface' : 'text-on-surface-variant'}>
              {departmentLabel(role)}
            </span>
          </span>
        )
      })}
      <span className={`font-data-tabular ${tone} text-on-surface-variant/70`}>
        {signatureSummary(roles, signed)}
      </span>
    </div>
  )
}

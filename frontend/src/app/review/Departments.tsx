import { ReasoningLine } from '../design/ReasoningLine'
import type { EventStatus } from '../lib/types'

/**
 * The order every screen renders departments in.
 *
 * Fixed and shared, so four blocks never reorder between two surfaces. It matches
 * `roles.DEPARTMENT_ORDER` on the server, and the two are the same statement made twice: the
 * server decides who owns a rule, this decides where they appear.
 */
export const DEPARTMENT_ORDER = ['engineering', 'procurement', 'production', 'quality'] as const

/** What Scenario B calls each desk, which is not always what the routing table calls it. */
const LABEL: Record<string, string> = {
  engineering: 'DESIGN',
  procurement: 'PROCUREMENT',
  production: 'PRODUCTION',
  quality: 'QUALITY',
}

export function departmentLabel(role: string): string {
  return LABEL[role] ?? role.toUpperCase()
}

export type DeskCheck = {
  rule: string
  scope: string | null
  status: EventStatus
  detail: string
  margin: string | null
  departments: string[]
}

const CHECK_MARK: Record<EventStatus, { icon: string; tone: string }> = {
  satisfied: { icon: 'check_circle', tone: 'text-[#4ade80]' },
  failed: { icon: 'cancel', tone: 'text-error' },
  evidence_missing: { icon: 'help', tone: 'text-tertiary-container' },
  not_applicable: { icon: 'remove', tone: 'text-on-surface-variant' },
}

/**
 * Every check under the desk that owns it.
 *
 * **One finding, several renderings, over one shared result.** Scenario B settled this on
 * 4 September: *"each role sees the same verdict in its own terms. One finding, three
 * renderings — a view layer over one shared result, never three engines."* This is the view
 * layer. Nothing is recomputed; the departments come off the frame, which the server derived
 * from the one routing table both the graph and the matrix already read.
 *
 * A rule with two owners appears under **both**. `part_qualification` is engineering's
 * judgement and quality's record, and a reader at either desk needs to see it.
 *
 * The three rules the engine declares it does not answer are **not** here. They have their
 * own line in the change request, which is where coverage honesty belongs — see BUILD.md's
 * second governing rule.
 */
export function groupByDepartment<T extends { departments: string[]; status: EventStatus }>(
  checks: readonly T[],
): Array<[string, T[]]> {
  const grouped = new Map<string, T[]>()
  for (const check of checks) {
    if (check.status === 'not_applicable') continue
    for (const role of check.departments.length > 0 ? check.departments : ['engineering']) {
      const held = grouped.get(role)
      if (held) held.push(check)
      else grouped.set(role, [check])
    }
  }
  return DEPARTMENT_ORDER.filter((role) => grouped.has(role)).map(
    (role) => [role, grouped.get(role) as T[]],
  )
}

/** Whether a check is one of the signed-in reader's own.
 *
 * **Everyone sees every check, and the reader sees which are theirs.** They are not filtered,
 * and that is a deliberate departure from the obvious access rule. A change order is one
 * controlled object with one audit trail: a desk signing it is signing the whole change, and
 * a signatory who cannot see procurement's objection is signing something they were not
 * shown. The PLM convention is the same one — reviews are routed concurrently and *each
 * function reviews the same change against its own criteria* — and the documented failure
 * mode of splitting them is a stakeholder who cannot see a dependency outside their own
 * column until it is expensive.
 *
 * So the answer is emphasis rather than a filter. `mine` is the desk the reader is signed in
 * as, and it is the only thing this decides.
 */
export function isMine(departments: readonly string[], mine: readonly string[]): boolean {
  const owners = departments.length > 0 ? departments : ['engineering']
  return owners.some((role) => mine.includes(role))
}

/** The accent a row wears when it is the reader's own desk's business.
 *
 * A left border rather than a colour change on the text: the verdict's own colour already
 * carries satisfied or failed, and a second colour meaning a second thing on the same line is
 * how a reader loses the first one. The words stay the same size and place, because this is a
 * change of emphasis and not a second document.
 */
export const MINE_ACCENT = 'border-l-2 border-primary-container pl-sm -ml-[2px]'

/** One desk's block: its name, then its own verdicts in the same marks the trace uses. */
export function DepartmentBlock({
  role,
  checks,
  mine = false,
}: {
  role: string
  checks: readonly DeskCheck[]
  /** This is the reader's own desk. Same content, said louder — see `isMine`. */
  mine?: boolean
}) {
  const failed = checks.filter((check) => check.status === 'failed').length

  return (
    <section className={`flex flex-col gap-xs ${mine ? MINE_ACCENT : ''}`}>
      <h4 className="flex items-baseline gap-sm px-sm pt-2 font-data-tabular text-[10px] uppercase">
        <span className={mine ? 'text-on-surface' : 'text-on-surface-variant/70'}>
          {departmentLabel(role)}
        </span>
        {mine ? <span className="text-primary-container">your desk</span> : null}
        {/* Words, not a colour: which approvals are missing must survive greyscale and a
            projector. */}
        <span className={failed > 0 ? 'text-error' : 'text-on-surface-variant/50'}>
          {failed > 0
            ? `${failed} failed of ${checks.length}`
            : `${checks.length} checked, nothing failed`}
        </span>
      </h4>
      {checks.map((check, index) => {
        const mark = CHECK_MARK[check.status]
        return (
          <ReasoningLine
            detail={`${check.detail}${check.margin ? ` · ${check.margin} to spare` : ''}`}
            icon={mark.icon}
            iconClassName={mark.tone}
            key={`${check.rule}:${check.scope ?? ''}:${index}`}
            text={`${check.rule.replace(/_/g, ' ')}${check.scope ? ` · ${check.scope}` : ''}`}
          />
        )
      })}
    </section>
  )
}

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

/** One desk's block: its name, then its own verdicts in the same marks the trace uses. */
export function DepartmentBlock({ role, checks }: { role: string; checks: readonly DeskCheck[] }) {
  const failed = checks.filter((check) => check.status === 'failed').length

  return (
    <section className="flex flex-col gap-xs">
      <h4 className="flex items-baseline gap-sm px-sm pt-2 font-data-tabular text-[10px] uppercase">
        <span className="text-on-surface-variant/70">{departmentLabel(role)}</span>
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

import { departmentLabel } from './Departments'
import { SignatureRow } from './Signatures'
import type { WaitingDecision } from '../lib/api'

/**
 * What this desk owes, at the top of the page where changes arrive.
 *
 * **This was a page of its own and it should never have been.** Signing already worked from
 * the review lane, so `/approvals` was a second place to answer the same question — which is
 * how one decision came to have two screens, and how the count of what a desk owed ended up
 * on the one nobody was looking at. The rail badge moved here too; the reader who has to
 * sign something is reading the change, not a queue about it.
 *
 * It is still a queue rather than a review: the desk's own reason to care, who else has
 * signed, and a way in. Reading a design trace to sign for procurement is exactly the round
 * trip this product removes, so the trace stays one click away rather than in the way.
 */
export function WaitingOnYou({
  decisions,
  onOpen,
}: {
  decisions: readonly WaitingDecision[]
  onOpen: (noticeId: string) => void
}) {
  const mine = decisions.filter((decision) => decision.mine.length > 0)
  if (mine.length === 0) return null

  return (
    <section className="shrink-0 border border-tertiary-container/60 rounded bg-surface-container-low p-md space-y-sm">
      <p className="m-0 font-data-tabular text-[11px] tracking-[0.08em] text-tertiary-container uppercase">
        {mine.length} waiting on you
      </p>
      {mine.map((decision) => (
        <article className="space-y-1" key={decision.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-md gap-y-0.5">
            <p className="m-0 font-data-tabular text-[13px] text-on-surface">
              {decision.line_name}
              <span className="text-on-surface-variant">
                {' '}
                · {decision.refdes.toUpperCase()} · {decision.retiring} → {decision.proposal}
              </span>
            </p>
            {decision.notice_id ? (
              <button
                className="h-7 px-md shrink-0 border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors"
                onClick={() => onOpen(decision.notice_id as string)}
                type="button"
              >
                OPEN THIS CHANGE
              </button>
            ) : null}
          </div>

          {/* Ticks rather than a sentence. *Two of four* is the same statement in the shape
              the eye scans, and the desk names stay beside the marks so the row survives
              greyscale and a projector. */}
          <SignatureRow roles={decision.roles} signed={decision.signed} tone="text-[11px]" />

          <p className="m-0 font-data-tabular text-[11px] text-on-surface-variant leading-relaxed">
            {decision.gate_rule
              ? `${decision.gate_rule.replace(/_/g, ' ')} failed, and ${departmentLabel(decision.mine[0] ?? '')} is being asked to accept it.`
              : decision.detail}
          </p>
        </article>
      ))}
    </section>
  )
}

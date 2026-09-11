import { departmentLabel } from './Departments'
import { SignatureRow } from './Signatures'
import type { ChangeRequest, WaitingDecision } from '../lib/api'

/**
 * What this desk owes, and the one place a change is signed.
 *
 * **This was a page of its own and it should never have been.** Signing already worked from
 * the review lane, so `/approvals` was a second place to answer the same question, which is
 * how one decision came to have two screens and how the count of what a desk owed ended up on
 * the one nobody was looking at. It is a pane now, at the top of the page where changes
 * arrive, and the rail badge moved here with it.
 *
 * **And it is where the signature happens, in one block rather than two.** The lane used to
 * carry `must sign`, the question, the two buttons and the four ticks, and the change request
 * carried the same four ticks again under APPROVALS. One document, two statements of who had
 * signed it. The buttons and the ticks belong with the reason the desk is being asked, which
 * is here; the lane keeps the question and the reasoning, which is what a reader following the
 * trace wants.
 *
 * **The desk's own checks are here too.** The lane shows every department, because a signatory
 * signs the whole change and hiding another desk's objection would be asking them to sign
 * something they were not shown. What belongs next to the signature is the part that is about
 * *this* desk, so it is the block this asks a person to answer for.
 */
export function WaitingOnYou({
  decisions,
  requests,
  busy,
  onOpen,
  onAnswer,
}: {
  decisions: readonly WaitingDecision[]
  /** The change requests, so a decision can show the checks its own desk owns. */
  requests: readonly ChangeRequest[]
  busy: string | null
  onOpen: (noticeId: string) => void
  onAnswer: (decision: WaitingDecision, approve: boolean) => void
}) {
  const mine = decisions.filter((decision) => decision.mine.length > 0)
  if (mine.length === 0) return null

  return (
    <section className="shrink-0 border border-tertiary-container/60 rounded bg-surface-container-low p-md space-y-md">
      <p className="m-0 font-data-tabular text-[11px] tracking-[0.08em] text-tertiary-container uppercase">
        {mine.length} waiting on you
      </p>
      {mine.map((decision) => {
        const request = requests.find((row) => row.line_id === decision.line_id)
        // The desk's own block, and every desk it owes for. A person holding two desks owes
        // for both, so this is a list rather than one.
        const own = (request?.departments ?? []).filter((desk) =>
          decision.mine.includes(desk.role),
        )
        const owed = decision.mine.map(departmentLabel).join(' and ')

        return (
          <article className="space-y-sm border-t border-outline-variant pt-sm first:border-t-0 first:pt-0" key={decision.id}>
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
                  className="h-7 px-md shrink-0 border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:border-on-surface-variant transition-colors"
                  onClick={() => onOpen(decision.notice_id as string)}
                  type="button"
                >
                  THE NOTICE
                </button>
              ) : null}
            </div>

            {/* Ticks rather than a sentence. *Two of four* is the same statement in the shape
                the eye scans, and the desk names stay beside the marks so the row survives
                greyscale and a projector. */}
            <SignatureRow roles={decision.roles} signed={decision.signed} tone="text-[11px]" />

            {/* **This desk's own checks**, which is the half of "every department, checked at
                once" that a person has to answer for. Everything the other three found is on
                the document on the right, because a change order is one object and a desk
                signing it is signing all of it. */}
            {own.map((desk) => (
              <div className="space-y-0.5" key={desk.role}>
                <p className="m-0 font-data-tabular text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">
                  {departmentLabel(desk.role)}
                  <span className={desk.failed > 0 ? 'text-error' : 'text-[#4ade80]'}>
                    {' '}
                    {desk.failed > 0
                      ? `${desk.failed} failed of ${desk.satisfied + desk.failed}`
                      : `${desk.satisfied} checked, nothing failed`}
                  </span>
                </p>
                <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                  {desk.headline}
                </p>
              </div>
            ))}

            <p className="m-0 font-data-tabular text-[12px] text-on-surface leading-relaxed">
              {decision.gate_rule
                ? `${decision.gate_rule.replace(/_/g, ' ')} failed, and ${owed} is being asked to accept it. `
                : ''}
              {decision.detail}
            </p>

            {decision.mine.length > 0 ? (
              <div className="flex gap-sm">
                <button
                  className="h-8 px-md border border-primary-container rounded font-data-tabular text-[12px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={busy === decision.id}
                  onClick={() => onAnswer(decision, true)}
                  type="button"
                >
                  {busy === decision.id
                    ? 'SIGNING…'
                    : `SIGN FOR ${decision.mine.map(departmentLabel).join(' AND ')}`}
                </button>
                <button
                  className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[12px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={busy === decision.id}
                  onClick={() => onAnswer(decision, false)}
                  type="button"
                >
                  LEAVE IT
                </button>
              </div>
            ) : null}
          </article>
        )
      })}
    </section>
  )
}

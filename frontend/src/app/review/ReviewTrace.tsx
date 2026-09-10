import { useEffect, useMemo, useRef } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import type { LineCheck, LineRequest } from '../lib/api'
import type { EventStatus } from '../lib/types'
import { DepartmentBlock, departmentLabel, groupByDepartment } from './Departments'
import type { LineReview, TraceItem } from './useLineReview'

/** How a check reads once it has an answer.
 *
 *  Five labels, five marks. Satisfied and failed are the two a reader acts on; the other
 *  three say the engine declined to answer, which is a different thing from a pass and does
 *  not get a pass's tick. */
const CHECK_MARK: Record<EventStatus, { icon: string; tone: string }> = {
  satisfied: { icon: 'check_circle', tone: 'text-[#4ade80]' },
  failed: { icon: 'cancel', tone: 'text-error' },
  evidence_missing: { icon: 'help', tone: 'text-tertiary-container' },
  not_assessed: { icon: 'remove', tone: 'text-on-surface-variant' },
  not_applicable: { icon: 'remove', tone: 'text-on-surface-variant' },
}

/**
 * One line of the trace, and what mark it carries.
 *
 * **Colour in this panel means a rule's verdict and nothing else.** Narration is what the
 * run is doing, not a result, so it is neutral — a green tick beside *"159 °C junction
 * against a 150 °C limit"* is the single most important sentence in the whole flow wearing
 * the mark of a pass. The same discipline the graph's colours are held to.
 */
function label(item: TraceItem): { icon: string; tone: string; text: string; detail?: string } {
  if (item.kind === 'error') {
    return { icon: 'error', tone: 'text-error', text: item.text }
  }
  if (item.kind === 'said') {
    return { icon: 'chevron_right', tone: 'text-on-surface-variant', text: item.text }
  }
  const mark = CHECK_MARK[item.status]
  return {
    icon: mark.icon,
    tone: item.accepted ? 'text-tertiary-container' : mark.tone,
    text: `${item.accepted ? 'FAILED · ACCEPTED · ' : ''}${item.rule.replace(/_/g, ' ')}${item.scope ? ` · ${item.scope}` : ''}`,
    detail: `${item.detail}${item.margin ? ` · ${item.margin} to spare` : ''}`,
  }
}

/** The trace, cut into runs of narration and runs of verdicts.
 *
 *  A contiguous run of checks is rendered as department blocks; everything else keeps the
 *  order it was said in. Splitting rather than sorting is what keeps the narration honest:
 *  the run really did say those things in that order. */
type Segment =
  | { kind: 'said'; items: TraceItem[] }
  | { kind: 'checks'; items: Array<Extract<TraceItem, { kind: 'check' }>> }

function segments(trace: readonly TraceItem[]): Segment[] {
  const out: Segment[] = []
  for (const item of trace) {
    const kind = item.kind === 'check' ? 'checks' : 'said'
    const tail = out[out.length - 1]
    if (tail && tail.kind === kind) {
      ;(tail.items as TraceItem[]).push(item)
    } else {
      out.push({ kind, items: [item] } as Segment)
    }
  }
  return out
}

function Verdict({ review }: { review: LineReview }) {
  if (review.status === 'running') {
    return (
      <span className="font-data-tabular text-[10px] text-primary-container">
        {review.trying ? `TRYING ${review.trying}` : 'CHECKING…'}
      </span>
    )
  }
  if (review.proposal) {
    return (
      <span
        className={`font-data-tabular text-[10px] px-sm py-0.5 border rounded ${
          review.settled === 'approved'
            ? 'border-[#4ade80] text-[#4ade80]'
            : review.conditional
              ? 'border-tertiary-container text-tertiary-container'
              : 'border-outline-variant text-[#4ade80]'
        }`}
      >
        {review.proposal}
      </span>
    )
  }
  if (review.status === 'done') {
    return (
      <span className="font-data-tabular text-[10px] px-sm py-0.5 border border-error rounded text-error">
        NO VIABLE PART
      </span>
    )
  }
  return null
}

/**
 * The review, beside the board it is about.
 *
 * The design workspace's trace panel, reading a review's frames instead of a design run's.
 * The decision lands here because this is where the person watching already is: on the
 * product, next to the picture of the part being replaced.
 *
 * **It is a pane, not a popover, so it does not close.** It briefly had a CLOSE button,
 * which made the workspace's left third vanish and took the board toggle with it — a
 * control that removes a third of the screen and part of another is not a control anybody
 * wants.
 *
 * What is coming for this product is **not** here. It was, briefly, and it was wrong for the
 * same reason the banner above the page was: an end-of-life notice is this board's conflict,
 * and a conflict opens in the drawer on the right. See `NoticePanel`.
 */
export function slotsWith(check: LineCheck | null, status: 'conflict' | 'accepted') {
  return Object.entries(check?.slots ?? {}).filter(([, slot]) => slot.status === status)
}

/**
 * Whether the board's resting statement is shown above the trace.
 *
 * Nothing has been said about this board yet — no live run and no stored one replayed —
 * means the check is the only account there is. Once a trace exists it is normally the
 * better account of the same board and this stands down for it.
 *
 * **An accepted failure is the exception.** The trace *predates* the signature: it recorded
 * the moment the rule failed, and no later frame can be added to it without rewriting what
 * the run actually said. Read on its own it leaves a red rule on screen with no resolution
 * anywhere on the page. This sentence is what resolves it, and it is about the board as it
 * stands now rather than about the run.
 */
export function showsRestingStatement(traceLength: number, acceptedCount: number): boolean {
  return traceLength === 0 || acceptedCount > 0
}

export function ReviewTrace({
  review,
  check,
  requests,
  onOpenRequest,
}: {
  review: LineReview
  /** What the engine found on this product line as it stands, from the per-visit check. */
  check: LineCheck | null
  requests: LineRequest[]
  onOpenRequest: (request: LineRequest) => void
}) {
  const tail = useRef<HTMLDivElement | null>(null)
  const cut = useMemo(() => segments(review.trace), [review.trace])

  useEffect(() => {
    if (review.trace.length > 0) {
      tail.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [review.trace.length, review.question, review.applied])

  // Not `status === 'idle'`: a replayed review reaches `done` the moment the page loads, and
  // the change request is exactly what a finished one should offer. What must not show it is
  // a run in flight.
  const idle = review.status !== 'running'
  const failing = slotsWith(check, 'conflict')
  const accepted = slotsWith(check, 'accepted')
  const resting = showsRestingStatement(review.trace.length, accepted.length)

  return (
    <aside className="w-1/4 min-w-[280px] max-w-[400px] flex-shrink-0 flex flex-col min-h-0 panel-border rounded-lg overflow-hidden bg-surface-container-low">
      <header className="h-10 px-md flex items-center justify-between gap-sm border-b border-outline-variant bg-surface-container-high flex-shrink-0">
        <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
          THE REVIEW
        </h2>
        <Verdict review={review} />
      </header>

      <div className="flex-1 overflow-y-auto p-sm flex flex-col gap-xs bg-[#0B0C0E]">
        {/* What the engine found on this product as it stands.
            
            Two jobs. It gives the green picture a number a reader can hold — the colour is
            computed and this says what computed it — and it is where a **failure** finally
            gets a sentence: a rule failing used to paint a part red and say nothing
            anywhere, which is a red nobody can act on. It goes only when nothing is
            running, because once a review starts the trace is the better account.

            Note what is deliberately *not* here: what could not be checked. Coverage
            honesty belongs in the change request, where somebody is deciding whether to
            sign. See BUILD.md's second governing rule. */}
        {resting && check ? (
          <>
            {/* Scoped, because *nothing failed* beside a part the graph has painted red
                reads as a contradiction. It is not one: a notice is a manufacturer saying a
                part is going away, and no rule has failed on the board as it stands today.
                Two different statements about two different moments, and the heading is
                what keeps them apart. */}
            <h3 className="font-data-tabular text-[10px] text-on-surface-variant/70 px-sm pt-1 uppercase">
              The engine, on the parts fitted today
            </h3>
            {failing.map(([refdes, slot]) => (
              <ReasoningLine
                detail={slot.detail ?? undefined}
                icon="cancel"
                iconClassName="text-error"
                key={refdes}
                text={`${refdes.toUpperCase()} fails a check on this product line`}
              />
            ))}
            {/* Beside an outstanding failure rather than instead of it. A board can carry
                both, and an accepted one that disappeared whenever something else failed
                would be a signature the screen stopped mentioning. */}
            {accepted.map(([refdes, slot]) => (
              <ReasoningLine
                detail={slot.detail ?? undefined}
                icon="warning"
                iconClassName="text-tertiary-container"
                key={refdes}
                text={`${refdes.toUpperCase()} failed and accepted: ${slot.accepted
                  .join(', ')
                  .replace(/_/g, ' ')}`}
              />
            ))}
            {failing.length === 0 && accepted.length === 0 ? (
              <ReasoningLine
                icon="check_circle"
                iconClassName="text-[#4ade80]"
                text={`${check.checked} checks, nothing failed`}
              />
            ) : null}
          </>
        ) : null}

        {/* Narration in the order it was said, and the verdicts under the desk that owns
            them. The run emits every check in one burst after the candidate loop, so a
            contiguous run of them is one moment rather than a sequence, and grouping it
            loses no ordering a reader could perceive. Everything else stays chronological,
            because it is a story about what happened. */}
        {cut.map((segment, index) =>
          segment.kind === 'checks' ? (
            groupByDepartment(segment.items).map(([role, checks]) => (
              <DepartmentBlock checks={checks} key={`${index}:${role}`} role={role} />
            ))
          ) : (
            segment.items.map((item, position) => {
              const { icon, tone, text, detail } = label(item)
              const last =
                index === cut.length - 1 &&
                position === segment.items.length - 1 &&
                review.status === 'running'
              return (
                <ReasoningLine
                  detail={detail}
                  icon={last ? 'progress_activity' : icon}
                  iconClassName={last ? 'text-primary-container' : tone}
                  key={`${index}:${position}`}
                  spinner={last}
                  text={text}
                />
              )
            })
          ),
        )}

        {review.question ? (
          <div className="flex flex-col flex-shrink-0 border border-outline-variant bg-[#16181D] rounded mt-sm overflow-hidden shadow-[0_4px_12px_rgba(0,0,0,0.5)]">
            <div className="flex items-start gap-sm px-sm py-2 bg-surface-container-high border-b border-outline-variant">
              <span
                className="material-symbols-outlined text-[14px] text-tertiary-container mt-[2px]"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                help
              </span>
              <span className="font-data-tabular text-[12px] font-semibold text-tertiary-container">
                Action Required
              </span>
            </div>
            <div className="p-sm flex flex-col gap-sm">
              <p className="font-body-sm text-body-sm text-on-surface leading-relaxed">
                {review.question.text}
              </p>
              {/* Whose it is, before the buttons. The server refuses an answer from a desk
                  with no standing here, and being told that after pressing approve is too
                  late. **And** rather than **or**: a substitution on a released design is
                  signed by every department that examined it, so this is the list of
                  people it needs, not a choice between them. */}
              {review.question.roles.length > 0 ? (
                <p className="font-data-tabular text-[10px] text-on-surface-variant uppercase">
                  {review.question.roles.map(departmentLabel).join(' and ')} must sign
                </p>
              ) : null}
              <div className="flex gap-sm">
                <button
                  className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={review.answering}
                  onClick={() => void review.answer(true)}
                  type="button"
                >
                  {review.answering
                    ? 'SIGNING…'
                    : review.question.roles.length > 1
                      ? 'SIGN FOR MY DESK'
                      : 'APPROVE AND APPLY'}
                </button>
                <button
                  className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={review.answering}
                  onClick={() => void review.answer(false)}
                  type="button"
                >
                  LEAVE IT
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Signed, and not enough. Words rather than a colour or a position, because which
            approvals are missing has to survive greyscale and a projector. */}
        {review.signatures && review.signatures.outstanding.length > 0 ? (
          <p className="font-data-tabular text-[11px] text-tertiary-container px-sm py-2 leading-relaxed">
            Signed by {review.signatures.signed.map(departmentLabel).join(' and ')}. Waiting on{' '}
            {review.signatures.outstanding.map(departmentLabel).join(' and ')}.
          </p>
        ) : null}

        {review.applied ? (
          <p className="font-data-tabular text-[11px] text-[#4ade80] px-sm py-2">
            Applied · {review.applied}
          </p>
        ) : null}

        {review.settled === 'declined' ? (
          <p className="font-data-tabular text-[11px] text-on-surface-variant px-sm py-2">
            Left as it is. The board still carries the retired part.
          </p>
        ) : null}

        {review.status === 'done' && !review.proposal && review.reason ? (
          <p className="font-data-tabular text-[11px] text-error px-sm py-2 leading-relaxed">
            {review.reason}
          </p>
        ) : null}

        {review.error ? (
          <p className="font-data-tabular text-[11px] text-error px-sm py-2">{review.error}</p>
        ) : null}

        {/* The change request, at the end of the trace rather than in place of it.
            
            The trace above is *how* this board reached its answer, and it is what somebody
            on this product wants. The change request is the **document** — cost, approvals,
            the board consequence, and the two coverage admissions — and it is what somebody
            signing wants. `/changes` already lists it for every affected line, so putting it
            here as the answer to clicking a notice made the page a second copy of that. One
            line, reachable, not in the way. */}
        {idle && requests.length > 0 ? (
          <div className="flex-shrink-0 mt-sm border-t border-outline-variant/40 pt-sm">
            {requests.map((request) => (
              <button
                className="w-full text-left px-sm py-1 rounded hover:bg-surface-variant/50 transition-colors flex items-center gap-sm"
                key={request.id}
                onClick={() => onOpenRequest(request)}
                type="button"
              >
                <span className="material-symbols-outlined text-[14px] text-on-surface-variant">
                  description
                </span>
                <span className="font-data-tabular text-[11px] text-on-surface-variant">
                  Change request · {request.proposal ?? 'no viable part'}
                </span>
              </button>
            ))}
          </div>
        ) : null}

        <div ref={tail} />
      </div>
    </aside>
  )
}

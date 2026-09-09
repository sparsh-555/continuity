import { useEffect, useRef } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import type { LineCheck, LineNotice, LineRequest } from '../lib/api'
import type { EventStatus } from '../lib/types'
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
    tone: mark.tone,
    text: `${item.rule.replace(/_/g, ' ')}${item.scope ? ` · ${item.scope}` : ''}`,
    detail: `${item.detail}${item.margin ? ` · ${item.margin} to spare` : ''}`,
  }
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
 * wants. What is coming for this product goes at the top of it, because the notice is the
 * reason to run anything and it belongs in the pane a reader is already in rather than in a
 * banner across the page.
 */
export function ReviewTrace({
  review,
  check,
  notices,
  requests,
  onStart,
  onOpenNotice,
}: {
  review: LineReview
  /** What the engine found on this product line as it stands, from the per-visit check. */
  check: LineCheck | null
  notices: LineNotice[]
  requests: LineRequest[]
  onStart: (notice: LineNotice) => void
  onOpenNotice: (noticeId: string) => void
}) {
  const tail = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (review.trace.length > 0) {
      tail.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [review.trace.length, review.question, review.applied])

  const idle = review.status === 'idle'
  const failing = Object.entries(check?.slots ?? {}).filter(
    ([, slot]) => slot.status === 'conflict',
  )

  return (
    <aside className="w-[400px] flex-shrink-0 flex flex-col min-h-0 panel-border rounded-lg overflow-hidden bg-surface-container-low">
      <header className="h-10 px-md flex items-center justify-between gap-sm border-b border-outline-variant bg-surface-container-high flex-shrink-0">
        <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
          THE REVIEW
        </h2>
        <Verdict review={review} />
      </header>

      <div className="flex-1 overflow-y-auto p-sm flex flex-col gap-xs bg-[#0B0C0E]">
        {/* What is coming for this product, and the only button that matters on this page. */}
        {notices.map((notice) => (
          <div
            className="flex-shrink-0 border border-error/60 bg-error-container/10 rounded p-sm space-y-sm"
            key={notice.id}
          >
            <div>
              <p className="font-data-tabular text-[11px] text-error leading-relaxed">
                {notice.mpn} at {notice.refdes.join(', ').toUpperCase()} is end of life
                {notice.effective_date ? ` · last order ${notice.effective_date}` : ''}
              </p>
              <p className="font-data-tabular text-[10px] text-on-surface-variant mt-1 leading-relaxed">
                {notice.manufacturer ?? 'manufacturer not stated'}
                {notice.replacement_mpn ? ` recommends ${notice.replacement_mpn}` : ''}
              </p>
            </div>
            <div className="flex items-center gap-sm">
              <button
                className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                disabled={review.status === 'running'}
                onClick={() => onStart(notice)}
                type="button"
              >
                {review.status === 'running'
                  ? 'RUNNING…'
                  : review.trace.length > 0
                    ? 'REVIEW AGAIN'
                    : 'REVIEW THIS LINE'}
              </button>
              <button
                className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors"
                onClick={() => onOpenNotice(notice.id)}
                type="button"
              >
                THE NOTICE
              </button>
            </div>
          </div>
        ))}

        {/* What the engine found on this product as it stands.
            
            Two jobs. It gives the green picture a number a reader can hold — the colour is
            computed and this says what computed it — and it is where a **failure** finally
            gets a sentence: a rule failing used to paint a part red and say nothing
            anywhere, which is a red nobody can act on. It goes only when nothing is
            running, because once a review starts the trace is the better account.

            Note what is deliberately *not* here: what could not be checked. Coverage
            honesty belongs in the change request, where somebody is deciding whether to
            sign. See BUILD.md's second governing rule. */}
        {idle && check ? (
          failing.length > 0 ? (
            failing.map(([refdes, slot]) => (
              <ReasoningLine
                detail={slot.detail ?? undefined}
                icon="cancel"
                iconClassName="text-error"
                key={refdes}
                text={`${refdes.toUpperCase()} fails a check on this product line`}
              />
            ))
          ) : (
            <ReasoningLine
              icon="check_circle"
              iconClassName="text-[#4ade80]"
              text={`${check.checked} checks, nothing failed`}
            />
          )
        ) : null}

        {review.trace.map((item, index) => {
          const { icon, tone, text, detail } = label(item)
          const last = index === review.trace.length - 1 && review.status === 'running'
          return (
            <ReasoningLine
              detail={detail}
              icon={last ? 'progress_activity' : icon}
              iconClassName={last ? 'text-primary-container' : tone}
              key={index}
              spinner={last}
              text={text}
            />
          )
        })}

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
              {/* Whose it is, before the buttons. The server refuses an answer from the
                  wrong desk, and being told that after pressing approve is too late. */}
              {review.question.roles.length > 0 ? (
                <p className="font-data-tabular text-[10px] text-on-surface-variant uppercase">
                  {review.question.roles.join(' or ')} decides
                </p>
              ) : null}
              <div className="flex gap-sm">
                <button
                  className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                  disabled={review.answering}
                  onClick={() => void review.answer(true)}
                  type="button"
                >
                  {review.answering ? 'APPLYING…' : 'APPROVE AND APPLY'}
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

        {/* What has already been decided here, when nothing is running. Stored, and until
            now written by every review and read by nothing. */}
        {idle && requests.length > 0 ? (
          <div className="flex-shrink-0 mt-sm space-y-1">
            <h3 className="font-data-tabular text-[10px] text-on-surface-variant/70 px-sm uppercase">
              Already decided here
            </h3>
            {requests.map((request) => (
              <button
                className="w-full text-left px-sm py-1 rounded hover:bg-surface-variant/50 transition-colors"
                key={request.id}
                onClick={() => request.notice_id && onOpenNotice(request.notice_id)}
                type="button"
              >
                <span className="font-data-tabular text-[11px] text-on-surface">
                  {request.proposal ?? 'no viable part'}
                </span>
                <span className="block font-data-tabular text-[10px] text-on-surface-variant">
                  {new Date(request.created_at).toLocaleDateString()}
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

import { useEffect, useRef } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
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

/**
 * The review, beside the board it is about.
 *
 * The same panel the design workspace puts next to its graph, reading a review's frames
 * instead of a design run's. The decision lands here because this is where the person
 * watching already is: on the product, next to the picture of the part being replaced.
 */
export function ReviewTrace({ review, onDismiss }: { review: LineReview; onDismiss: () => void }) {
  const tail = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    tail.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [review.trace.length, review.question, review.applied])

  return (
    <aside className="w-[400px] flex-shrink-0 flex flex-col border border-outline-variant rounded bg-surface-container-low overflow-hidden">
      <header className="px-md py-sm border-b border-outline-variant flex items-center justify-between gap-sm">
        <h2 className="font-label-caps text-label-caps uppercase text-on-surface-variant">
          THE REVIEW
        </h2>
        <div className="flex items-center gap-sm">
          {review.status === 'running' ? (
            <span className="font-data-tabular text-[10px] text-primary-container">
              {review.trying ? `TRYING ${review.trying}` : 'CHECKING…'}
            </span>
          ) : review.proposal ? (
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
          ) : review.status === 'done' ? (
            <span className="font-data-tabular text-[10px] px-sm py-0.5 border border-error rounded text-error">
              NO VIABLE PART
            </span>
          ) : null}
          <button
            className="font-data-tabular text-[10px] text-on-surface-variant hover:text-on-surface"
            onClick={() => {
              review.stop()
              onDismiss()
            }}
            type="button"
          >
            CLOSE
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-sm flex flex-col gap-xs bg-[#0B0C0E]">
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

        <div ref={tail} />
      </div>
    </aside>
  )
}

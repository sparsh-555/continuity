import { useCallback, useEffect, useRef, useState } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import { departmentLabel } from './Departments'
import { noticeReviews, type NoticeReview, type ReviewFrame } from '../lib/api'
import type { EventStatus } from '../lib/types'
import { runReview } from '../lib/reviewStream'
import {
  emptyLanes,
  lanesFromReview,
  pacedDelay,
  reduceFrame,
  rollingTrace,
  withSignatures,
  type Lane,
  type LaneState,
  type LaneCheck,
  type LaneTraceItem,
} from './laneState'

const CHECK_MARK: Record<EventStatus, { icon: string; tone: string }> = {
  satisfied: { icon: 'check_circle', tone: 'text-[#4ade80]' },
  failed: { icon: 'cancel', tone: 'text-error' },
  evidence_missing: { icon: 'help', tone: 'text-tertiary-container' },
  not_applicable: { icon: 'remove', tone: 'text-on-surface-variant' },
}

/** An icon reinforces a verdict; it never carries the verdict on its own. */
export function checkLabel(check: Pick<LaneCheck, 'status' | 'accepted'>): string {
  if (check.status === 'failed' && check.accepted) return 'ACCEPTED FAILURE'
  return {
    satisfied: 'SATISFIED',
    failed: 'FAILED',
    evidence_missing: 'EVIDENCE MISSING',
    not_applicable: 'NOT APPLICABLE',
  }[check.status]
}

function checkText(check: LaneCheck): string {
  const owners = check.departments.length > 0
    ? ` · ${check.departments.map(departmentLabel).join(' / ')}`
    : ''
  return `${checkLabel(check)} · ${check.rule.replace(/_/g, ' ')}${check.scope ? ` · ${check.scope}` : ''}${owners}`
}

function traceText(item: LaneTraceItem): string {
  return item.kind === 'said' ? item.text : checkText(item)
}

/** The words one frame puts on screen, for the row and for the pace it is given.
 *
 * The pace is measured against what the reader has to get through, so the two cannot be
 * allowed to come from different places: a frame whose line is drawn from one function and
 * timed from another is a frame timed against text nobody sees. */
export function frameText(frame: ReviewFrame): string {
  switch (frame.type) {
    case 'candidate':
      return `Trying ${frame.part.mpn}.`
    case 'check':
      return checkText(frame)
    case 'reasoning':
      return frame.text
    case 'line_done':
      return frame.reason ?? ''
    default:
      return ''
  }
}

/**
 * Every affected product line, re-checked at the same time, one row each.
 *
 * A team answers an end-of-life notice in sequence: design proposes, procurement replies,
 * production objects, and that sequence is where the 48 hours goes. These run together, on
 * one stream, and end in three different places.
 *
 * **Rows, not columns, and the change is deliberate.** What has to land here is
 * *simultaneity* and then *disagreement*. Three side-by-side columns of 10px monospace all
 * writing at once is noise on a projector, nobody reads three traces in parallel, and five
 * affected lines would have made five columns unreadable. One legible row each, and **the
 * three verdicts then read down a single column**, which is the comparison this whole
 * scenario exists to point at. A row expands in place for the product worth going deep on,
 * and expanding one does not collapse the others.
 *
 * **This pane is the run and nothing else.** The signature moved to the pane that is about
 * the desk being asked, and the change request moved to the pane on the right, where a reader
 * can compare it against another board without losing the trace they came from. What is left
 * here is the thing this column is for: three boards advancing together.
 *
 * **A run is drawn at reading pace, and a finished one is painted whole.** Frames off the
 * live stream go into a queue and are drawn one at a time by one timer, because with the
 * distributor replayed the whole run arrives in a burst and a burst is not watchable. Frames
 * read back from the database are not queued at all: the run is over, and a reader who
 * returns to the page wants where it ended rather than a second performance.
 */
export function ReviewLanes({
  noticeId,
  candidates,
  openLineId,
  onOpenLine,
  onFinished,
}: {
  noticeId: string
  candidates: string[]
  /** Which board's change request is on the right, so the row that owns it can say so. */
  openLineId: string | null
  onOpenLine: (lineId: string | null) => void
  /** A run ended, so the documents read from it are stale. */
  onFinished?: () => void
}) {
  /** One state object rather than five, because the reducer owns the whole of it. */
  const [state, setState] = useState<LaneState>(emptyLanes)
  const { lanes, preamble } = state
  const [open, setOpen] = useState<Set<string>>(new Set())
  /** The connection is open. */
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abort = useRef<(() => void) | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Frames waiting to be drawn, oldest first. */
  const queue = useRef<ReviewFrame[]>([])
  const draining = useRef(false)
  /** How far through the run the pace is, so the wobble does not reset on every frame. */
  const position = useRef(0)
  /** The signatures the run left, applied once the queue is empty. They are not frames: the
   *  live path learns them from the answer to a signing call, not from the stream. */
  const rows = useRef<NoticeReview[]>([])
  /** Whether a live run owns the screen, read from a ref rather than from state a closure
   *  captured: an updater must stay pure, and React calls one twice under `StrictMode`,
   *  which `./demo.sh` runs. */
  const live = useRef(false)

  useEffect(() => () => abort.current?.(), [])

  /** Draw one frame, then wait, then draw the next.
   *
   * The frame is taken out of the queue as a value rather than read from an index when the
   * update runs. The replay used to reach into a mutable cursor from inside a `setState`
   * updater, which React runs at render time rather than at hand-over time, so by then later
   * steps had already advanced it past the end and the reducer was handed `undefined`. A
   * queue of values cannot get ahead of itself. */
  const drain = useCallback(() => {
    const frame = queue.current.shift()
    if (!frame) {
      draining.current = false
      const stored = rows.current
      if (stored.length > 0) {
        setState((current) => withSignatures(current, stored))
      }
      return
    }
    position.current += 1
    setState((current) => reduceFrame(current, frame))
    timer.current = setTimeout(drain, pacedDelay(frameText(frame), position.current))
  }, [])

  const enqueue = useCallback(
    (frames: readonly ReviewFrame[]) => {
      if (frames.length === 0) return
      queue.current.push(...frames)
      if (draining.current) return
      draining.current = true
      drain()
    },
    [drain],
  )

  const start = useCallback(() => {
    abort.current?.()
    if (timer.current) clearTimeout(timer.current)
    queue.current = []
    draining.current = false
    rows.current = []
    position.current = 0
    live.current = true
    setState(emptyLanes)
    setOpen(new Set())
    setError(null)
    setStreaming(true)

    abort.current = runReview(
      { noticeId, candidates },
      // Every frame goes through the same queue and the same reducer a read-back run uses,
      // so a running review and a recorded one cannot come to mean different things on the
      // way to the screen.
      (frame: ReviewFrame) => enqueue([frame]),
      setError,
      () => {
        live.current = false
        setStreaming(false)
        // **The documents were read before this run and are now the previous run's.** They
        // are asked for again the moment it ends, so `RUN IT AGAIN` cannot leave last
        // night's numbers sitting under this morning's trace.
        onFinished?.()
      },
    )
  }, [candidates, enqueue, noticeId, onFinished])

  /**
   * Coming back to a notice shows the review that ran, not just its conclusions.
   *
   * **The stored frames are painted whole, not played.** The complete trace, its questions,
   * its verdicts and its signatures, in one pass through the same reducer a live run uses —
   * so a reader who left the page and came back sees what the run concluded rather than
   * watching it conclude again. It is a read, so it never starts a run and never overwrites
   * one: a live run or a `RUN IT AGAIN` replaces the hydration exactly as it replaced what
   * was there before.
   */
  useEffect(() => {
    let active = true
    noticeReviews(noticeId)
      .then((stored: NoticeReview[]) => {
        // A run that started while this was in flight owns the screen now.
        if (!active || stored.length === 0 || live.current) return
        rows.current = stored
        setState(lanesFromReview(stored))
      })
      .catch(() => {
        // A review that cannot be read is not an error worth a banner: the page still has
        // its notices and its change requests, and RUN IT AGAIN is still there.
      })

    return () => {
      active = false
    }
  }, [noticeId])

  /**
   * **One lane open at a time.** The rows stay visible and keep advancing, which is the
   * simultaneity, and the one a reader opened owns the room its trace needs. Opening a
   * second used to leave the first open too, which put two traces in one column again.
   */
  const toggle = (lineId: string) =>
    setOpen((current) => (current.has(lineId) ? new Set<string>() : new Set([lineId])))

  return (
    // **A named region, so the run is addressable.** The notice row now carries what the
    // notice reaches, which names the same product lines the lanes do, so "the button called
    // Sensor node" stopped being one button. Naming the region answers that for a screen
    // reader and for anything else that has to point at this pane rather than at the page.
    <section aria-label="The review" className="space-y-md">
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          {lanes.length > 0 ? `${lanes.length} product lines, checked together` : 'The review'}
        </h2>
        <button
          className="h-8 px-md border border-primary-container rounded font-data-tabular text-[12px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
          disabled={streaming}
          onClick={start}
          type="button"
        >
          {streaming ? 'RUNNING…' : lanes.length > 0 ? 'RUN IT AGAIN' : 'START THE REVIEW'}
        </button>
      </div>

      {error ? <p className="font-data-tabular text-[12px] text-error">{error}</p> : null}

      {/* Discovery happens once for the whole review, because the same part is retired on
          every board, so it is said once above the lanes rather than three times inside. */}
      {preamble.length > 0 ? (
        <div className="space-y-1 border border-outline-variant rounded p-md bg-surface-container-low">
          {preamble.map((line, index) => (
            <p
              className="font-data-tabular text-[13px] text-on-surface-variant leading-relaxed"
              key={index}
            >
              {line}
            </p>
          ))}
        </div>
      ) : null}

      {lanes.length > 0 ? (
        <div className="border border-outline-variant rounded bg-surface-container-low overflow-hidden">
          {lanes.map((lane, index) => {
            const expanded = open.has(lane.lineId)
            const isOpen = openLineId === lane.lineId
            // The newest thing this board has said, for a lane that has finished.
            const latest =
              lane.error ??
              lane.applied ??
              (lane.trace.length > 0 ? traceText(lane.trace[lane.trace.length - 1]) : '')
            // **While it is still arriving, the last few lines rather than the last one.** A
            // single line replaced every few hundred milliseconds shows that something is
            // happening and cannot be read; three show the trace moving.
            const moving = rollingTrace(lane.trace, lane.running)
            const askedToo = [...lane.trace].reverse().find((item) => item.kind === 'said')?.text
            const renderItem = (item: LaneTraceItem, position: number) => {
              if (item.kind === 'said') {
                return (
                  <ReasoningLine
                    icon="chevron_right"
                    iconClassName="text-on-surface-variant"
                    key={position}
                    text={item.text}
                  />
                )
              }
              const mark = CHECK_MARK[item.status]
              return (
                <ReasoningLine
                  detail={`${item.detail}${item.margin ? ` · ${item.margin} to spare` : ''}`}
                  icon={mark.icon}
                  iconClassName={mark.tone}
                  key={`${item.rule}:${item.scope ?? ''}:${position}`}
                  text={traceText(item)}
                />
              )
            }
            return (
              <article
                className={index > 0 ? 'border-t border-outline-variant' : undefined}
                key={lane.lineId}
              >
                <div
                  className={`w-full px-md py-sm flex items-center gap-md ${
                    isOpen ? 'bg-surface-container-high' : ''
                  }`}
                >
                  <button
                    aria-expanded={expanded}
                    // **`overflow-hidden`, because a flex child that overflows does not clip itself.** At a
                    // laptop width the name and the newest line are both truncated, and a truncated
                    // flex item still paints its full text unless an ancestor clips it, so the board
                    // name ran under its own verdict chip.
                    className="flex items-center gap-md flex-1 min-w-0 overflow-hidden text-left hover:opacity-90 transition-opacity"
                    onClick={() => toggle(lane.lineId)}
                    type="button"
                  >
                    <span
                      aria-hidden
                      className={`material-symbols-outlined text-[18px] text-on-surface-variant transition-transform ${
                        expanded ? 'rotate-90' : ''
                      }`}
                    >
                      chevron_right
                    </span>
                    {/* **A fixed name column, and narrower than it was.** At a laptop width the middle
                        pane has about five hundred pixels and the row also carries a verdict and a
                        way into the document; two hundred pixels of name left the newest line
                        truncated to nothing and pushed the chip into the name. Names are short and
                        the full one is on the row's own title. */}
                    <span
                      className="font-data-tabular text-[14px] text-on-surface w-[180px] flex-shrink-0 truncate"
                      title={lane.name}
                    >
                      {lane.name}
                    </span>
                    <span className="font-data-tabular text-[12px] text-on-surface-variant flex-1 min-w-0 truncate">
                      {lane.running ? '' : latest}
                    </span>
                  </button>
                  <span className="flex-shrink-0">
                    <Verdict lane={lane} />
                  </span>
                  {/* **The way into this board's document.** The change request is about one
                      product, and a reader comparing two of them should be able to switch
                      without losing the trace they came from. */}
                  <button
                    className={`h-7 px-md shrink-0 border rounded font-data-tabular text-[11px] transition-colors ${
                      isOpen
                        ? 'border-primary-container text-primary-container'
                        : 'border-outline-variant text-on-surface-variant hover:border-on-surface-variant'
                    }`}
                    onClick={() => onOpenLine(isOpen ? null : lane.lineId)}
                    type="button"
                  >
                    {isOpen ? 'CLOSE' : 'THE CHANGE REQUEST'}
                  </button>
                </div>

                {expanded ? (
                  <div className="px-md pb-sm pl-[46px] space-y-0.5 bg-[#0B0C0E]">
                    {lane.trace.map(renderItem)}
                    {!lane.running && !lane.proposal && lane.reason ? (
                      <p className="font-data-tabular text-[12px] text-error px-sm py-1 leading-relaxed">
                        {lane.reason}
                      </p>
                    ) : null}
                  </div>
                ) : lane.running && moving.length > 0 ? (
                  <div className="px-md pb-sm pl-[46px] space-y-0.5">
                    {moving.map((item, position) => renderItem(item, position))}
                  </div>
                ) : null}

                {/* **The question, and nothing to press.** A desk being asked needs the
                    sentence it is answering, which is why it stays out of the fold. The
                    buttons and the four ticks are on the pane that is about that desk, in the
                    one block that states who has signed. Two statements of the same thing is
                    how one document came to disagree with itself about who had signed it. */}
                {lane.question ? (
                  <div className="px-md pb-md pl-[46px] space-y-sm">
                    <p className="font-data-tabular text-[11px] tracking-[0.08em] text-tertiary-container uppercase">
                      {lane.question.roles.map(departmentLabel).join(' and ')} must sign
                    </p>
                    <p className="font-body-md text-[14px] text-on-surface leading-relaxed">
                      {lane.question.text}
                    </p>
                    {askedToo ? (
                      <p className="font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                        {askedToo}
                      </p>
                    ) : null}
                    <p className="font-data-tabular text-[12px] text-on-surface-variant">
                      Signing is on the left, under what is waiting on you.
                    </p>
                  </div>
                ) : null}

                {lane.settled === 'declined' ? (
                  <p className="px-md pb-sm pl-[46px] font-data-tabular text-[12px] text-on-surface-variant">
                    Left as it is. The board still carries the retired part.
                  </p>
                ) : null}
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function Verdict({ lane }: { lane: Lane }) {
  if (lane.error) {
    return <span className="font-data-tabular text-[12px] text-error">FAILED</span>
  }
  if (lane.running) {
    return (
      <span className="font-data-tabular text-[12px] text-primary-container">CHECKING…</span>
    )
  }
  if (!lane.proposal) {
    return (
      <span className="font-data-tabular text-[12px] px-sm py-0.5 border border-error rounded text-error whitespace-nowrap">
        NO VIABLE PART
      </span>
    )
  }
  return (
    <span
      className={`font-data-tabular text-[12px] px-sm py-0.5 border rounded whitespace-nowrap ${
        lane.settled === 'approved'
          ? 'border-[#4ade80] text-[#4ade80]'
          : lane.conditional
            ? 'border-tertiary-container text-tertiary-container'
            : 'border-outline-variant text-[#4ade80]'
      }`}
    >
      {lane.proposal}
    </span>
  )
}

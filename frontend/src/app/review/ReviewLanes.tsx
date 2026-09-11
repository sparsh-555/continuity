import { useCallback, useEffect, useRef, useState } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import { useAuth } from '../hooks/useAuth'
import { departmentLabel } from './Departments'
import { RequestCard } from './RequestCard'
import {
  ApiError,
  answerDecision,
  noticeReviews,
  type ChangeRequest,
  type NoticeReview,
  type ReviewFrame,
} from '../lib/api'
import type { EventStatus } from '../lib/types'
import { runReview } from '../lib/reviewStream'
import {
  emptyLanes,
  hasSigned,
  pacedDelay,
  reduceFrame,
  replayFrames,
  seededLanes,
  withSignatures,
  type Lane,
  type LaneState,
  type LaneCheck,
  type LaneTraceItem,
} from './laneState'

const NO_ROLES: string[] = []

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

function traceText(item: LaneTraceItem): string {
  if (item.kind === 'said') return item.text
  const owners = item.departments.length > 0
    ? ` · ${item.departments.map(departmentLabel).join(' / ')}`
    : ''
  return `${checkLabel(item)} · ${item.rule.replace(/_/g, ' ')}${item.scope ? ` · ${item.scope}` : ''}${owners}`
}

function Verdict({ lane }: { lane: Lane }) {
  if (lane.error) {
    return <span className="font-data-tabular text-[11px] text-error">FAILED</span>
  }
  if (lane.running) {
    return (
      <span className="font-data-tabular text-[11px] text-primary-container">CHECKING…</span>
    )
  }
  if (!lane.proposal) {
    return (
      <span className="font-data-tabular text-[11px] px-sm py-0.5 border border-error rounded text-error whitespace-nowrap">
        NO VIABLE PART
      </span>
    )
  }
  return (
    <span
      className={`font-data-tabular text-[11px] px-sm py-0.5 border rounded whitespace-nowrap ${
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

/**
 * Every affected product line, re-checked at the same time — one row each.
 *
 * A team answers an end-of-life notice in sequence: design proposes, procurement replies,
 * production objects, and that sequence is where the 48 hours goes. These run together, on
 * one stream, and end in three different places.
 *
 * **Rows, not columns, and the change is deliberate.** What has to land here is
 * *simultaneity* and then *disagreement*. Three side-by-side columns of 10px monospace all
 * writing at once is noise on a projector, nobody reads three traces in parallel, and five
 * affected lines would have made five columns unreadable. One legible row each — the
 * product, what it is trying, its state — makes the parallelism obvious, and **the three
 * verdicts then read down a single column**, which is the comparison this whole scenario
 * exists to point at. A row expands in place for the product worth going deep on, and
 * expanding one does not collapse the others.
 */
export function ReviewLanes({
  noticeId,
  candidates,
  requests = [],
  onApplied,
}: {
  noticeId: string
  candidates: string[]
  /** The change requests, one per affected product line, to sit at the end of their lane. */
  requests?: ChangeRequest[]
  /** A product line changed, so anything showing it is stale. */
  onApplied?: (lineId: string) => void
}) {
  /** One state object rather than five, because the reducer owns the whole of it. */
  const [state, setState] = useState<LaneState>(emptyLanes)
  const { lanes, preamble } = state
  // Whose eyes this is. The lane has to know, because whether a question may be signed is
  // about the desk reading it rather than about the board it is on.
  const { user } = useAuth()
  const myRoles = user?.roles ?? NO_ROLES
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [replaying, setReplaying] = useState(false)
  const abort = useRef<(() => void) | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const replay = useRef<{
    frames: ReviewFrame[]
    next: number
    rows: NoticeReview[]
  } | null>(null)
  const skip = useRef<(() => void) | null>(null)
  /** Whether a live run owns the screen, read from the stream rather than from state a
   *  closure captured: an updater must stay pure, and React calls one twice under
   *  `StrictMode`, which `./demo.sh` runs. */
  const runningRef = useRef(false)

  useEffect(() => () => abort.current?.(), [])

  const patch = useCallback((lineId: string, change: Partial<Lane>) => {
    setState((current) => ({
      ...current,
      lanes: current.lanes.map((lane) =>
        lane.lineId === lineId ? { ...lane, ...change } : lane,
      ),
    }))
  }, [])

  const start = useCallback(() => {
    abort.current?.()
    // A replay in flight must not keep painting over the run somebody just asked for.
    if (timer.current) clearTimeout(timer.current)
    replay.current = null
    setReplaying(false)
    runningRef.current = true
    setState(emptyLanes)
    setOpen(new Set())
    setError(null)
    setRunning(true)

    abort.current = runReview(
      { noticeId, candidates },
      // Every frame goes through the same reducer a replay uses, so a running review and a
      // read-back one cannot come to mean different things on the way to the screen.
      (frame: ReviewFrame) => setState((current) => reduceFrame(current, frame)),
      setError,
      () => {
        runningRef.current = false
        setRunning(false)
      },
    )
  }, [candidates, noticeId])

  /**
   * Coming back to a notice shows the review that ran, not just its conclusions.
   *
   * The run is assembled from stored frames through the same reducer the live stream uses.
   * It is a read, so it never starts a run and never overwrites one: a live run or a second
   * `RUN IT AGAIN` replaces the hydration exactly as it replaces a finished live run.
   */
  useEffect(() => {
    let active = true
    noticeReviews(noticeId)
      .then((rows: NoticeReview[]) => {
        // A run that started while this was in flight owns the screen now.
        if (!active || rows.length === 0 || runningRef.current) return

        const frames = replayFrames(rows)
        replay.current = { frames, next: 0, rows }
        setState(seededLanes(rows))
        setReplaying(frames.length > 0)

        // **One frame at a time, at reading pace.** The whole run arrives in a single
        // response, so without this a recorded review is over before anybody can read it —
        // which is what a demonstration cannot afford and what the recording makes cheap to
        // fix. Nothing here claims the model is working: it is a recording played back, and
        // the pace is the only thing being changed.
        const step = () => {
          const current = replay.current
          if (!active || !current) return
          // **The frame is captured before the update is enqueued, and that is load-bearing.**
          // An updater reads its closure when React runs it, not when it is handed over, so an
          // updater reaching into `current.next` at render time reads an index that later steps
          // have already advanced — and once it has passed the end, `reduceFrame` is handed
          // `undefined` and the page goes with it. React also calls an updater twice under
          // `StrictMode`, which `./demo.sh` runs, so it has to be a pure function of what it
          // closes over.
          const frame = current.frames[current.next]
          if (!frame) {
            finish()
            return
          }
          current.next += 1
          setState((state) => reduceFrame(state, frame))
          timer.current = setTimeout(step, pacedDelay(current.next))
        }
        timer.current = setTimeout(step, pacedDelay(0))
      })
      .catch(() => {
        // A replay that cannot be read is not an error worth a banner: the page still has
        // its notices and its change requests, and RUN IT AGAIN is still there.
      })

    /** Everything that is left, at once — for somebody who does not want to wait. */
    function finish() {
      const current = replay.current
      if (current) {
        setState((state) =>
          withSignatures(
            current.frames.slice(current.next).reduce(reduceFrame, state),
            current.rows,
          ),
        )
      }
      replay.current = null
      setReplaying(false)
      if (timer.current) clearTimeout(timer.current)
    }
    skip.current = finish

    return () => {
      active = false
      if (timer.current) clearTimeout(timer.current)
    }
  }, [noticeId])

  const answer = useCallback(
    async (lane: Lane, approve: boolean) => {
      if (!lane.question) return
      setBusy(lane.lineId)
      try {
        const outcome = await answerDecision(lane.question.decisionId, approve)
        // Three outcomes. `pending` means this desk signed and the change is waiting on the
        // rest, so the question goes and nothing has been applied.
        patch(lane.lineId, {
          settled: outcome.state === 'pending' ? null : outcome.state,
          signatures:
            outcome.signed || outcome.outstanding
              ? { signed: outcome.signed ?? [], outstanding: outcome.outstanding ?? [] }
              : null,
          question: null,
          refusal: null,
          applied:
            outcome.state === 'approved' && outcome.mpn
              ? `${outcome.refdes?.toUpperCase()} is ${outcome.mpn}${
                  outcome.revision ? ` · ${outcome.revision}` : ''
                }`
              : null,
        })
        if (outcome.state === 'approved') onApplied?.(lane.lineId)
      } catch (caught) {
        patch(lane.lineId, {
          // The server's own sentence. A 403 here names the desk that owns the decision,
          // which is the only useful thing it could say. **Into `refusal`, not `error`**: the
          // row renders `error` as FAILED, and a refusal to sign twice is not a board that
          // failed a check.
          refusal:
            caught instanceof ApiError
              ? (caught.message ?? 'That decision could not be answered.')
              : 'That decision could not be answered.',
        })
      } finally {
        setBusy(null)
      }
    },
    [onApplied, patch],
  )

  /**
   * **One lane open at a time.** This is the master-detail the page is: the rows stay
   * visible and keep advancing, which is the simultaneity, and the one a reader opened owns
   * the room its trace needs. Opening a second used to leave the first open too, which put
   * two traces in one column again and is the shape this page was rebuilt to stop being.
   */
  const toggle = (lineId: string) =>
    setOpen((current) => (current.has(lineId) ? new Set<string>() : new Set([lineId])))

  return (
    <section className="space-y-md">
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-data-tabular text-[11px] text-on-surface-variant">
          {lanes.length > 0 ? `${lanes.length} PRODUCT LINES, CHECKED TOGETHER` : 'THE REVIEW'}
        </h2>
        <div className="flex items-center gap-sm">
          {/* Offered only while a replay is actually playing, and it says what it does: a
              reader who has seen enough should not have to wait out a recording. */}
          {replaying ? (
            <button
              className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:bg-surface-variant transition-colors"
              onClick={() => skip.current?.()}
              type="button"
            >
              SKIP TO THE END
            </button>
          ) : null}
          <button
            className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={running}
            onClick={start}
            type="button"
          >
            {running ? 'RUNNING…' : lanes.length > 0 ? 'RUN IT AGAIN' : 'START THE REVIEW'}
          </button>
        </div>
      </div>

      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      {/* Discovery happens once for the whole review — the same part is retired on every
          board — so it is said once, above the lanes, rather than three times inside them. */}
      {preamble.length > 0 ? (
        <div className="space-y-1 border border-outline-variant rounded p-md bg-surface-container-low">
          {preamble.map((line, index) => (
            <p
              className="font-data-tabular text-[11px] text-on-surface-variant leading-relaxed"
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
            // One line, and it is the newest thing this board has said. A lane that
            // scrolled its own trace would be a column again.
            const latest = lane.error ?? lane.applied ?? (lane.trace.length > 0 ? traceText(lane.trace[lane.trace.length - 1]) : '')
            // The last thing the run *said*, for the signing box: a verdict line repeats
            // what the row already shows, and what a signature rests on is the reasoning.
            const askedToo = [...lane.trace].reverse().find((item) => item.kind === 'said')?.text
            return (
              <article
                className={index > 0 ? 'border-t border-outline-variant' : undefined}
                key={lane.lineId}
              >
                <button
                  aria-expanded={expanded}
                  className="w-full text-left px-md py-sm flex items-center gap-md hover:bg-surface-variant/40 transition-colors"
                  onClick={() => toggle(lane.lineId)}
                  type="button"
                >
                  <span
                    className={`material-symbols-outlined text-[18px] text-on-surface-variant transition-transform ${
                      expanded ? 'rotate-90' : ''
                    }`}
                  >
                    chevron_right
                  </span>
                  <span className="font-data-tabular text-[12px] text-on-surface w-[180px] flex-shrink-0 truncate">
                    {lane.name}
                  </span>
                  <span className="font-data-tabular text-[11px] text-on-surface-variant flex-1 min-w-0 truncate">
                    {latest}
                  </span>
                  <span className="flex-shrink-0">
                    <Verdict lane={lane} />
                  </span>
                </button>

                {expanded ? (
                  <div className="px-md pb-sm pl-[46px] space-y-1 bg-[#0B0C0E]">
                    {lane.trace.map((item, position) => {
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
                    })}
                    {!lane.running && !lane.proposal && lane.reason ? (
                      <p className="font-data-tabular text-[11px] text-error px-sm py-1 leading-relaxed">
                        {lane.reason}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/* The question stays out of the fold. A decision waiting on a desk is the
                    one thing on this page nobody should have to expand a row to find. */}
                {lane.question ? (
                  <div className="px-md pb-md pl-[46px] space-y-sm">
                    {/* **And**, not **or**: every department that examined the change
                        signs it, so this is the list it needs rather than a choice. */}
                    <p className="font-data-tabular text-[10px] text-tertiary-container uppercase">
                      {lane.question.roles.map(departmentLabel).join(' and ')} must sign
                    </p>
                    <p className="font-data-tabular text-[11px] text-on-surface leading-relaxed">
                      {lane.question.text}
                    </p>
                    {/* **The argument, in one line, in the box where it is signed.** The
                        reader who has just watched the run arrive can see what it concluded
                        without expanding anything, and the whole trace stays one click above
                        for the one who wants to check it first. */}
                    {askedToo ? (
                      <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
                        {askedToo}
                      </p>
                    ) : null}
                    {/* **The same rule `/approvals` holds**: a desk that has already signed
                        sees what it signed and no buttons, rather than buttons that will 409.
                        This is the second place a question is answered, and a lane offering a
                        signature it already has is how the two places come to disagree. */}
                    {hasSigned(lane, myRoles) ? (
                      <p className="font-data-tabular text-[10px] text-on-surface-variant">
                        You have signed this. It is not yours to sign again.
                      </p>
                    ) : (
                      <div className="flex gap-sm">
                        <button
                          className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                          disabled={busy === lane.lineId}
                          onClick={() => void answer(lane, true)}
                          type="button"
                        >
                          {busy === lane.lineId
                            ? 'SIGNING…'
                            : lane.question.roles.length > 1
                              ? 'SIGN FOR MY DESK'
                              : 'APPROVE AND APPLY'}
                        </button>
                        <button
                          className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
                          disabled={busy === lane.lineId}
                          onClick={() => void answer(lane, false)}
                          type="button"
                        >
                          LEAVE IT
                        </button>
                      </div>
                    )}
                    {/* A refusal is about the desk, not about the board, so it is said here
                        and never becomes the lane's verdict. */}
                    {lane.refusal ? (
                      <p className="font-data-tabular text-[10px] text-error leading-relaxed">
                        {lane.refusal}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/* Signed, and waiting. In words, because which approvals are missing must
                    not depend on a colour or a position. */}
                {lane.signatures && lane.signatures.outstanding.length > 0 ? (
                  <p className="px-md pb-sm pl-[46px] font-data-tabular text-[10px] text-tertiary-container leading-relaxed">
                    Signed by {lane.signatures.signed.map(departmentLabel).join(' and ')}. Waiting
                    on {lane.signatures.outstanding.map(departmentLabel).join(' and ')}.
                  </p>
                ) : null}

                {lane.settled === 'declined' ? (
                  <p className="px-md pb-sm pl-[46px] font-data-tabular text-[10px] text-on-surface-variant">
                    Left as it is. The board still carries the retired part.
                  </p>
                ) : null}

                {/* **The change request is the lane's last layer, not a stack under the
                    run.** It is about this board, and the reader who has just followed this
                    trace is the reader who wants it. Under the lanes it arrived in the same
                    column as the run, which made a finished document look like the
                    replacement for a running one — and put the third product's request a
                    scroll away from the first. `/lines/:id` says the same thing with its
                    one-line summary at the end of its trace. */}
                {requests
                  .filter((request) => request.line_id === lane.lineId)
                  .map((request) => (
                    <div className="px-md pb-md pl-[46px]" key={request.line_id}>
                      <RequestCard request={request} />
                    </div>
                  ))}
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import { useAuth } from '../hooks/useAuth'
import { departmentLabel } from './Departments'
import { RequestCard } from './RequestCard'
import { RoundTrips } from './RoundTrips'
import { SignatureRow } from './Signatures'
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
  lanesFromReview,
  pacedDelay,
  reduceFrame,
  replayFrames,
  rollingTrace,
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

/** Which notices this tab has already watched run.
 *
 * **The run was being replayed from the beginning on every visit.** Leaving `/changes` and
 * coming back re-mounted the lanes, the hydration effect found the stored frames again, and
 * the whole review played over from the first line — so a reader who stepped away for the
 * change request came back to a trace starting again at nothing. A run this tab has already
 * seen is shown at its end, with the signatures, rather than performed twice.
 *
 * **In `sessionStorage` rather than in a module, because a refresh is a visit too.** A
 * module-level set survives client-side navigation and dies on F5, which is the wrong line to
 * draw: an accidental refresh four minutes into a walk-through would put the whole review
 * back to its first frame. Session scope is the lifetime the reader means by *come back to
 * the page* — this tab, this sitting — and a new tab is a new sitting and may watch again.
 *
 * Every access is guarded: private windows and blocked site data make `sessionStorage` throw
 * rather than return null, and a review that cannot remember having played should play.
 */
const PLAYED_KEY = 'continuity.review.played'

function readPlayed(): Set<string> {
  try {
    const raw = window.sessionStorage.getItem(PLAYED_KEY)
    return new Set<string>(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    return new Set<string>()
  }
}

function writePlayed(played: Set<string>): void {
  try {
    window.sessionStorage.setItem(PLAYED_KEY, JSON.stringify([...played]))
  } catch {
    // A tab that cannot remember replays. Losing the memory costs a replay, and throwing
    // here would cost the page.
  }
}

export function markPlayed(noticeId: string): void {
  const played = readPlayed()
  if (played.has(noticeId)) return
  played.add(noticeId)
  writePlayed(played)
}

export function hasPlayed(noticeId: string): boolean {
  return readPlayed().has(noticeId)
}

/** Between tests. Nothing in the product calls this. */
export function forgetPlayed(): void {
  writePlayed(new Set<string>())
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
 *
 * **Both paths to this screen now queue through one pace.** Frames arrive from the live
 * stream or from the database and go into the same queue, drawn by the same timer, so a
 * cached run and a running one are the same thing to watch. The live path used to bypass the
 * pace entirely, which is why START THE REVIEW finished before the browser had painted twice
 * while coming back to the page showed the trace arriving.
 */
export function ReviewLanes({
  noticeId,
  candidates,
  requests = [],
  onApplied,
  onFinished,
}: {
  noticeId: string
  candidates: string[]
  /** The change requests, one per affected product line, to sit at the end of their lane. */
  requests?: ChangeRequest[]
  /** A product line changed, so anything showing it is stale. */
  onApplied?: (lineId: string) => void
  /** A run ended, so the documents read from it are stale. */
  onFinished?: () => void
}) {
  /** One state object rather than five, because the reducer owns the whole of it. */
  const [state, setState] = useState<LaneState>(emptyLanes)
  const { lanes, preamble } = state
  // Whose eyes this is. The lane has to know, because whether a question may be signed is
  // about the desk reading it rather than about the board it is on.
  const { user } = useAuth()
  const myRoles = user?.roles ?? NO_ROLES
  const [open, setOpen] = useState<Set<string>>(new Set())
  /** The connection is open. */
  const [streaming, setStreaming] = useState(false)
  /** Frames are still being drawn. Outlives `streaming`: a stream that has closed can leave
   *  a queue behind it, and the run is not over on screen until the queue is empty. */
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
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

  const patch = useCallback((lineId: string, change: Partial<Lane>) => {
    setState((current) => ({
      ...current,
      lanes: current.lanes.map((lane) =>
        lane.lineId === lineId ? { ...lane, ...change } : lane,
      ),
    }))
  }, [])

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
      setPlaying(false)
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
      setPlaying(true)
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
    // Watched from here on. A reader who starts a run and then goes to look at a product
    // line comes back to its result, not to it starting again.
    markPlayed(noticeId)
    setState(emptyLanes)
    setOpen(new Set())
    setError(null)
    setPlaying(false)
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
   * The run is assembled from stored frames through the same reducer and the same queue the
   * live stream uses. It is a read, so it never starts a run and never overwrites one: a
   * live run or a second `RUN IT AGAIN` replaces the hydration exactly as it replaces a
   * finished live run.
   */
  useEffect(() => {
    let active = true
    noticeReviews(noticeId)
      .then((stored: NoticeReview[]) => {
        // A run that started while this was in flight owns the screen now.
        if (!active || stored.length === 0 || live.current) return

        rows.current = stored

        // **Already watched: shown at its end rather than performed again.** The stored
        // frames are applied in one pass, signatures and all, so the change request and the
        // signatures are where the reader left them.
        if (hasPlayed(noticeId)) {
          setState(lanesFromReview(stored))
          return
        }

        markPlayed(noticeId)
        setState(seededLanes(stored))
        enqueue(replayFrames(stored))
      })
      .catch(() => {
        // A replay that cannot be read is not an error worth a banner: the page still has
        // its notices and its change requests, and RUN IT AGAIN is still there.
      })

    return () => {
      active = false
    }
  }, [noticeId, enqueue])

  /** Everything that is left, at once — for somebody who does not want to wait. */
  const skip = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    const rest = queue.current
    const stored = rows.current
    queue.current = []
    draining.current = false
    setPlaying(false)
    setState((current) => {
      const applied = rest.reduce(reduceFrame, current)
      return stored.length > 0 ? withSignatures(applied, stored) : applied
    })
  }, [])

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
        // The queue is empty by the time anyone can press this, so the stored row is what
        // the signature landed on. Kept in step so a later skip does not paint the desk out
        // of a signature it has already given. Matched by line rather than by decision id:
        // one line carries one pending decision here, and the id on the wire has a prefix
        // the stored row does not.
        rows.current = rows.current.map((row) =>
          row.line_id === lane.lineId
            ? {
                ...row,
                signed: outcome.signed ?? row.signed,
                outstanding: outcome.outstanding ?? row.outstanding,
              }
            : row,
        )
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

  // **Said once, above the lanes.** The round trips a change did not have to cross are the
  // same three numbers on every board, because they are about the desks and the handoffs
  // rather than about the board — and printing the identical paragraph three times is what
  // made it read as boilerplate. The boards are what differ, and each lane still carries its
  // own change request in full.
  const roundTrips = requests.find((request) => request.saving)?.saving ?? null

  return (
    <section className="space-y-md">
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          {lanes.length > 0 ? `${lanes.length} product lines, checked together` : 'The review'}
        </h2>
        <div className="flex items-center gap-sm">
          {/* Offered whenever frames are still being drawn, which now includes a live run —
              a reader who has seen enough should not have to wait one out. */}
          {playing ? (
            <button
              className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[12px] text-on-surface-variant hover:bg-surface-variant transition-colors"
              onClick={skip}
              type="button"
            >
              SKIP TO THE END
            </button>
          ) : null}
          <button
            className="h-8 px-md border border-primary-container rounded font-data-tabular text-[12px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
            disabled={streaming}
            onClick={start}
            type="button"
          >
            {streaming ? 'RUNNING…' : lanes.length > 0 ? 'RUN IT AGAIN' : 'START THE REVIEW'}
          </button>
        </div>
      </div>

      {error ? <p className="font-data-tabular text-[12px] text-error">{error}</p> : null}

      {/* Discovery happens once for the whole review — the same part is retired on every
          board — so it is said once, above the lanes, rather than three times inside them. */}
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
            // The newest thing this board has said, for a lane that has finished.
            const latest =
              lane.error ??
              lane.applied ??
              (lane.trace.length > 0 ? traceText(lane.trace[lane.trace.length - 1]) : '')
            // **While it is still arriving, the last few lines rather than the last one.** A
            // single line replaced every few hundred milliseconds shows that something is
            // happening and cannot be read; three show the trace moving.
            const moving = rollingTrace(lane.trace, lane.running)
            // The last thing the run *said*, for the signing box: a verdict line repeats
            // what the row already shows, and what a signature rests on is the reasoning.
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
                  <span className="font-data-tabular text-[14px] text-on-surface w-[200px] flex-shrink-0 truncate">
                    {lane.name}
                  </span>
                  {/* Nothing here while the run is still arriving: the lines below carry it,
                      and repeating the newest one above them is the same sentence twice. */}
                  <span className="font-data-tabular text-[12px] text-on-surface-variant flex-1 min-w-0 truncate">
                    {lane.running ? '' : latest}
                  </span>
                  <span className="flex-shrink-0">
                    <Verdict lane={lane} />
                  </span>
                </button>

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

                {/* The question stays out of the fold. A decision waiting on a desk is the
                    one thing on this page nobody should have to expand a row to find. */}
                {lane.question ? (
                  <div className="px-md pb-md pl-[46px] space-y-sm">
                    {/* **And**, not **or**: every department that examined the change
                        signs it, so this is the list it needs rather than a choice. */}
                    <p className="font-data-tabular text-[11px] tracking-[0.08em] text-tertiary-container uppercase">
                      {lane.question.roles.map(departmentLabel).join(' and ')} must sign
                    </p>
                    <p className="font-body-md text-[14px] text-on-surface leading-relaxed">
                      {lane.question.text}
                    </p>
                    {/* **The argument, in one line, in the box where it is signed.** The
                        reader who has just watched the run arrive can see what it concluded
                        without expanding anything, and the whole trace stays one click above
                        for the one who wants to check it first. */}
                    {askedToo ? (
                      <p className="font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                        {askedToo}
                      </p>
                    ) : null}
                    {/* **A desk that has already signed** sees what it signed and no buttons,
                        rather than buttons that will 409. */}
                    {hasSigned(lane, myRoles) ? (
                      <p className="font-data-tabular text-[12px] text-on-surface-variant">
                        You have signed this. It is not yours to sign again.
                      </p>
                    ) : (
                      <div className="flex gap-sm">
                        <button
                          className="h-7 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
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
                          className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[11px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
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
                      <p className="font-data-tabular text-[12px] text-error leading-relaxed">
                        {lane.refusal}
                      </p>
                    ) : null}
                  </div>
                ) : null}

                {/* Signed, and waiting. In ticks rather than a sentence, because which
                    signatures are missing is the thing a reader is scanning for. */}
                {lane.signatures && lane.signatures.outstanding.length > 0 ? (
                  <div className="px-md pb-sm pl-[46px]">
                    <SignatureRow
                      roles={lane.signatures.signed.concat(lane.signatures.outstanding)}
                      signed={lane.signatures.signed}
                      tone="text-[11px]"
                    />
                  </div>
                ) : null}

                {lane.settled === 'declined' ? (
                  <p className="px-md pb-sm pl-[46px] font-data-tabular text-[12px] text-on-surface-variant">
                    Left as it is. The board still carries the retired part.
                  </p>
                ) : null}

                {/* **The change request is the lane's last layer, not a stack under the
                    run.** It is about this board, and the reader who has just followed this
                    trace is the reader who wants it. Under the lanes it arrived in the same
                    column as the run, which made a finished document look like the
                    replacement for a running one.

                    **And it is not drawn while a run is in flight.** These are the last
                    run's documents, and a finished proposal sitting under a trace that is
                    still arriving says the run has already concluded. The lane holds the
                    trace until the run it belongs to is over. */}
                {streaming
                  ? null
                  : requests
                      .filter((request) => request.line_id === lane.lineId)
                      .map((request) => (
                        <div className="px-md pb-md pl-[46px]" key={request.line_id}>
                          <RequestCard
                            request={request}
                            showRoundTrips={roundTrips === null}
                            signatures={lane.signatures}
                          />
                        </div>
                      ))}
              </article>
            )
          })}
        </div>
      ) : null}

      {roundTrips ? <RoundTrips saving={roundTrips} /> : null}
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

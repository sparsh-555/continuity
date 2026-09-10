import { useCallback, useEffect, useRef, useState } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import { departmentLabel } from './Departments'
import {
  ApiError,
  answerDecision,
  noticeReviews,
  type NoticeReview,
  type ReviewFrame,
} from '../lib/api'
import type { EventStatus } from '../lib/types'
import { runReview } from '../lib/reviewStream'
import {
  emptyLanes,
  lanesFromReview,
  reduceFrame,
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
  onApplied,
}: {
  noticeId: string
  candidates: string[]
  /** A product line changed, so anything showing it is stale. */
  onApplied?: (lineId: string) => void
}) {
  /** One state object rather than five, because the reducer owns the whole of it. */
  const [state, setState] = useState<LaneState>(emptyLanes)
  const { lanes, preamble } = state
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const abort = useRef<(() => void) | null>(null)

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
      () => setRunning(false),
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
        if (!active || rows.length === 0) return
        setState((current) =>
          // A run that started while this was in flight owns the screen now.
          current.lanes.length > 0 ? current : lanesFromReview(rows),
        )
      })
      .catch(() => {
        // A replay that cannot be read is not an error worth a banner: the page still has
        // its notices and its change requests, and RUN IT AGAIN is still there.
      })
    return () => {
      active = false
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
          // which is the only useful thing it could say.
          error:
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

  const toggle = (lineId: string) =>
    setOpen((current) => {
      const next = new Set(current)
      if (next.has(lineId)) next.delete(lineId)
      else next.add(lineId)
      return next
    })

  return (
    <section className="space-y-md">
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-data-tabular text-[11px] text-on-surface-variant">
          {lanes.length > 0 ? `${lanes.length} PRODUCT LINES, CHECKED TOGETHER` : 'THE REVIEW'}
        </h2>
        <button
          className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
          disabled={running}
          onClick={start}
          type="button"
        >
          {running ? 'RUNNING…' : lanes.length > 0 ? 'RUN IT AGAIN' : 'START THE REVIEW'}
        </button>
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
              </article>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

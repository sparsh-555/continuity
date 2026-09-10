import { useCallback, useEffect, useRef, useState } from 'react'

import { ReasoningLine } from '../design/ReasoningLine'
import { departmentLabel } from './Departments'
import { ApiError, answerDecision, type ReviewFrame } from '../lib/api'
import { runReview } from '../lib/reviewStream'

type Lane = {
  lineId: string
  name: string
  /** Everything this board's run has said, newest last. */
  said: string[]
  question: { decisionId: string; text: string; roles: string[] } | null
  proposal: string | null
  conditional: boolean
  reason: string
  running: boolean
  settled: 'approved' | 'declined' | null
  /** Which desks have signed and which have not, once anybody has. */
  signatures: { signed: string[]; outstanding: string[] } | null
  applied: string | null
  error: string | null
}

function fresh(lineId: string, name: string): Lane {
  return {
    lineId,
    name,
    said: [],
    question: null,
    proposal: null,
    conditional: false,
    reason: '',
    running: true,
    settled: null,
    signatures: null,
    applied: null,
    error: null,
  }
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
  const [lanes, setLanes] = useState<Lane[]>([])
  const [preamble, setPreamble] = useState<string[]>([])
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const abort = useRef<(() => void) | null>(null)

  useEffect(() => () => abort.current?.(), [])

  const update = useCallback((lineId: string, change: Partial<Lane>) => {
    setLanes((current) =>
      current.map((lane) => (lane.lineId === lineId ? { ...lane, ...change } : lane)),
    )
  }, [])

  const say = useCallback((lineId: string, text: string) => {
    setLanes((current) =>
      current.map((lane) =>
        lane.lineId === lineId ? { ...lane, said: [...lane.said, text] } : lane,
      ),
    )
  }, [])

  const start = useCallback(() => {
    abort.current?.()
    setLanes([])
    setPreamble([])
    setOpen(new Set())
    setError(null)
    setRunning(true)

    abort.current = runReview(
      { noticeId, candidates },
      (frame: ReviewFrame) => {
        switch (frame.type) {
          case 'review_started':
            setLanes(frame.lines.map((line) => fresh(line.line_id, line.name)))
            break
          case 'reasoning':
            if (frame.line_id) say(frame.line_id, frame.text)
            else setPreamble((current) => [...current, frame.text])
            break
          case 'question':
            update(frame.line_id, {
              question: {
                decisionId: frame.question_id.replace(/^decision:/, ''),
                text: frame.text,
                roles: frame.roles,
              },
            })
            break
          case 'line_done':
            update(frame.line_id, {
              running: false,
              proposal: frame.proposal,
              conditional: frame.conditional,
              reason: frame.reason,
            })
            break
          case 'error':
            if (frame.line_id) update(frame.line_id, { error: frame.message, running: false })
            else setError(frame.message)
            break
          default:
            break
        }
      },
      setError,
      () => setRunning(false),
    )
  }, [candidates, noticeId, say, update])

  const answer = useCallback(
    async (lane: Lane, approve: boolean) => {
      if (!lane.question) return
      setBusy(lane.lineId)
      try {
        const outcome = await answerDecision(lane.question.decisionId, approve)
        // Three outcomes. `pending` means this desk signed and the change is waiting on the
        // rest, so the question goes and nothing has been applied.
        update(lane.lineId, {
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
        update(lane.lineId, {
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
    [onApplied, update],
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
            const latest = lane.error ?? lane.applied ?? lane.said[lane.said.length - 1] ?? ''
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
                    {lane.said.map((line, position) => (
                      <ReasoningLine
                        icon="chevron_right"
                        iconClassName="text-on-surface-variant"
                        key={position}
                        text={line}
                      />
                    ))}
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

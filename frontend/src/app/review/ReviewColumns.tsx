import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, answerDecision, type ReviewFrame } from '../lib/api'
import { runReview } from '../lib/reviewStream'

type Column = {
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
  applied: string | null
  error: string | null
}

const RUNNING_LINES = 3
/** How much of a column's reasoning to keep on screen while it runs. Three boards writing
 *  at once is unreadable at full length, and the whole trace is on the product line. */

function fresh(lineId: string, name: string): Column {
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
    applied: null,
    error: null,
  }
}

function Verdict({ column }: { column: Column }) {
  if (column.error) {
    return <span className="font-data-tabular text-[11px] text-error">{column.error}</span>
  }
  if (column.running) {
    return (
      <span className="font-data-tabular text-[11px] text-on-surface-variant">CHECKING…</span>
    )
  }
  if (!column.proposal) {
    return (
      <span className="font-data-tabular text-[11px] px-sm py-0.5 border border-error rounded text-error">
        NO VIABLE PART
      </span>
    )
  }
  return (
    <span
      className={`font-data-tabular text-[11px] px-sm py-0.5 border rounded ${
        column.settled === 'approved'
          ? 'border-[#4ade80] text-[#4ade80]'
          : column.conditional
            ? 'border-tertiary-container text-tertiary-container'
            : 'border-outline-variant text-[#4ade80]'
      }`}
    >
      {column.proposal}
    </span>
  )
}

/** Every affected product line, re-checked at the same time.
 *
 *  A team answers an end-of-life notice in sequence — design proposes, procurement replies,
 *  production objects — and that sequence is where the 48 hours goes. These run together, on
 *  one stream, and end in three different places: applied, waiting on a desk that is not
 *  yours, or nothing that works. */
export function ReviewColumns({
  noticeId,
  candidates,
  onApplied,
}: {
  noticeId: string
  candidates: string[]
  /** A product line changed, so anything showing it is stale. */
  onApplied?: (lineId: string) => void
}) {
  const [columns, setColumns] = useState<Column[]>([])
  const [preamble, setPreamble] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const abort = useRef<(() => void) | null>(null)

  useEffect(() => () => abort.current?.(), [])

  const update = useCallback((lineId: string, change: Partial<Column>) => {
    setColumns((current) =>
      current.map((column) => (column.lineId === lineId ? { ...column, ...change } : column)),
    )
  }, [])

  const say = useCallback((lineId: string, text: string) => {
    setColumns((current) =>
      current.map((column) =>
        column.lineId === lineId ? { ...column, said: [...column.said, text] } : column,
      ),
    )
  }, [])

  const start = useCallback(() => {
    abort.current?.()
    setColumns([])
    setPreamble([])
    setError(null)
    setRunning(true)

    abort.current = runReview(
      noticeId,
      candidates,
      (frame: ReviewFrame) => {
        switch (frame.type) {
          case 'review_started':
            setColumns(frame.lines.map((line) => fresh(line.line_id, line.name)))
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
    async (column: Column, approve: boolean) => {
      if (!column.question) return
      setBusy(column.lineId)
      try {
        const outcome = await answerDecision(column.question.decisionId, approve)
        update(column.lineId, {
          settled: outcome.state,
          question: null,
          applied:
            outcome.state === 'approved' && outcome.mpn
              ? `${outcome.refdes?.toUpperCase()} is ${outcome.mpn}${
                  outcome.revision ? ` · ${outcome.revision}` : ''
                }`
              : null,
        })
        if (outcome.state === 'approved') onApplied?.(column.lineId)
      } catch (caught) {
        update(column.lineId, {
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

  return (
    <section className="space-y-md">
      <div className="flex items-center justify-between gap-md">
        <h2 className="font-data-tabular text-[11px] text-on-surface-variant">
          {columns.length > 0
            ? `${columns.length} PRODUCT LINES, CHECKED TOGETHER`
            : 'THE REVIEW'}
        </h2>
        <button
          className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
          disabled={running}
          onClick={start}
          type="button"
        >
          {running ? 'RUNNING…' : columns.length > 0 ? 'RUN IT AGAIN' : 'START THE REVIEW'}
        </button>
      </div>

      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      {/* Discovery happens once for the whole review — the same part is retired on every
          board — so it is said once, above the columns, rather than three times inside them. */}
      {preamble.length > 0 ? (
        <div className="space-y-1 border border-outline-variant rounded p-md bg-surface-container-low">
          {preamble.map((line, index) => (
            <p
              className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed"
              key={index}
            >
              {line}
            </p>
          ))}
        </div>
      ) : null}

      {columns.length > 0 ? (
        <div className="grid gap-md" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>
          {columns.map((column) => (
            <article
              className="border border-outline-variant rounded bg-surface-container-low flex flex-col"
              key={column.lineId}
            >
              <header className="px-md py-sm border-b border-outline-variant flex items-center justify-between gap-sm">
                <h3 className="font-data-tabular text-[11px] text-on-surface truncate">
                  {column.name}
                </h3>
                <Verdict column={column} />
              </header>

              <div className="px-md py-sm space-y-1 flex-1">
                {(column.running ? column.said.slice(-RUNNING_LINES) : column.said).map(
                  (line, index) => (
                    <p
                      className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed"
                      key={index}
                    >
                      {line}
                    </p>
                  ),
                )}
              </div>

              {column.question ? (
                <div className="px-md py-sm border-t border-outline-variant space-y-sm">
                  {/* Whose it is, before the buttons. A decision addressed to another desk
                      is refused at the server, and being told that after pressing approve
                      is being told too late. */}
                  <p className="font-data-tabular text-[10px] text-tertiary-container uppercase">
                    {column.question.roles.join(' or ')} decides
                  </p>
                  <p className="font-data-tabular text-[10px] text-on-surface leading-relaxed">
                    {column.question.text}
                  </p>
                  <div className="flex gap-sm">
                    <button
                      className="h-7 px-md border border-primary-container rounded font-data-tabular text-[10px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                      disabled={busy === column.lineId}
                      onClick={() => void answer(column, true)}
                      type="button"
                    >
                      {busy === column.lineId ? 'APPLYING…' : 'APPROVE AND APPLY'}
                    </button>
                    <button
                      className="h-7 px-md border border-outline-variant rounded font-data-tabular text-[10px] text-on-surface-variant hover:bg-surface-variant transition-colors disabled:opacity-40"
                      disabled={busy === column.lineId}
                      onClick={() => void answer(column, false)}
                      type="button"
                    >
                      LEAVE IT
                    </button>
                  </div>
                </div>
              ) : null}

              {column.applied ? (
                <p className="px-md py-sm border-t border-outline-variant font-data-tabular text-[10px] text-[#4ade80]">
                  Applied · {column.applied}
                </p>
              ) : null}

              {column.settled === 'declined' ? (
                <p className="px-md py-sm border-t border-outline-variant font-data-tabular text-[10px] text-on-surface-variant">
                  Left as it is. The board still carries the retired part.
                </p>
              ) : null}

              {!column.running && !column.proposal && column.reason ? (
                <p className="px-md py-sm border-t border-outline-variant font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
                  {column.reason}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, answerDecision, type ReviewFrame } from '../lib/api'
import { runReview } from '../lib/reviewStream'
import type { EventStatus } from '../lib/types'

/** One thing the run has said, in the order it said it. */
export type TraceItem =
  | { kind: 'said'; text: string }
  | {
      kind: 'check'
      rule: string
      scope: string | null
      status: EventStatus
      detail: string
      margin: string | null
      accepted: boolean
      /** The desks that own this rule, from the frame. */
      departments: string[]
    }
  | { kind: 'error'; text: string }

export type LineQuestion = { decisionId: string; text: string; roles: string[] }

export type LineReview = ReturnType<typeof useLineReview>

/**
 * One product line's review, run from the product line's own page.
 *
 * The same endpoint the company-wide run uses, narrowed by `line_id`, so there is exactly
 * one review in this product and both surfaces read the same frames. Discovery lines arrive
 * with no `line_id` — the part is retired everywhere, so the server says it once — and on a
 * page about one board there is nothing to separate them from, so they go in the trace where
 * they were spoken.
 */
export function useLineReview({
  lineId,
  onApplied,
}: {
  lineId: string
  /** The bill changed, so everything showing this product is stale. */
  onApplied?: () => void
}) {
  const [status, setStatus] = useState<'idle' | 'running' | 'done'>('idle')
  const [trace, setTrace] = useState<TraceItem[]>([])
  const [positions, setPositions] = useState<readonly string[]>([])
  const [trying, setTrying] = useState<string | null>(null)
  const [proposal, setProposal] = useState<string | null>(null)
  const [conditional, setConditional] = useState(false)
  const [reason, setReason] = useState('')
  const [question, setQuestion] = useState<LineQuestion | null>(null)
  const [settled, setSettled] = useState<'approved' | 'declined' | null>(null)
  /** Which desks have signed and which have not, once anybody has signed. */
  const [signatures, setSignatures] = useState<{ signed: string[]; outstanding: string[] } | null>(
    null,
  )
  const [applied, setApplied] = useState<string | null>(null)
  const [answering, setAnswering] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const abort = useRef<(() => void) | null>(null)

  // Abandoning the page cancels the run rather than leaving a stream writing into a
  // component that is gone.
  useEffect(() => () => abort.current?.(), [])

  const say = useCallback((item: TraceItem) => {
    setTrace((current) => [...current, item])
  }, [])

  /** One frame, live or replayed. Both read the same vocabulary, so a stored review and a
   *  running one cannot come to mean different things on the way to the screen. */
  const consume = useCallback(
    (frame: ReviewFrame) => {
      switch (frame.type) {
        case 'reasoning':
          // The engine's own answer to where it is working replaces the notice's, because
          // a notice can name a designator on a board the run then declines to touch.
          if (frame.slot) setPositions([frame.slot])
          say({ kind: 'said', text: frame.text })
          break
        case 'candidate':
          setPositions([frame.slot])
          setTrying(frame.part.mpn)
          break
        case 'check':
          say({
            kind: 'check',
            rule: frame.rule,
            scope: frame.scope,
            status: frame.status,
            detail: frame.detail,
            margin: frame.margin,
            accepted: frame.accepted,
            departments: frame.departments ?? [],
          })
          break
        case 'question':
          setQuestion({
            decisionId: frame.question_id.replace(/^decision:/, ''),
            text: frame.text,
            roles: frame.roles,
          })
          break
        case 'line_done':
          setProposal(frame.proposal)
          setConditional(frame.conditional)
          setReason(frame.reason)
          setTrying(frame.proposal)
          break
        case 'error':
          say({ kind: 'error', text: frame.message })
          break
        default:
          break
      }
    },
    [say],
  )

  const clear = useCallback((at: readonly string[]) => {
    setTrace([])
    setPositions(at)
    setTrying(null)
    setProposal(null)
    setConditional(false)
    setReason('')
    setQuestion(null)
    setSettled(null)
    setSignatures(null)
    setApplied(null)
    setError(null)
  }, [])

  /**
   * Start the run.
   *
   * The notice is an argument rather than a prop because a product line can carry more than
   * one, and the run is about the one whose banner was pressed.
   *
   * `at` is where that notice says the retired part sits, and seeding the working position
   * from it is the difference between the middle act of this story being visible and not.
   * **Measured:** the run's own first mention of the position arrives with the burst of
   * per-line frames at the very end — everything before it is discovery, which is about the
   * part rather than about this board — so a picture that waited for the engine to name the
   * slot showed it for a fraction of a second, twenty-five seconds after somebody pressed
   * the button. The notice already says where the part is, it needs nothing computed, and
   * the banner overhead is rendering the same fact.
   */
  const start = useCallback(
    (noticeId: string, at: readonly string[] = []) => {
      abort.current?.()
      setStatus('running')
      clear(at)
      abort.current = runReview(
        { noticeId, candidates: [], lineId },
        consume,
        setError,
        () => setStatus('done'),
      )
    },
    [clear, consume, lineId],
  )

  /**
   * A review that already happened, put back on screen.
   *
   * Through the same reducer the stream goes through, so what a reader sees of a finished
   * review is what they would have seen watching it. The one difference is the question: a
   * replayed run does not raise one, because whatever it was waiting for has been answered
   * or is still recorded as pending on the decision itself.
   */
  const hydrate = useCallback(
    (frames: ReviewFrame[], settledAs: 'approved' | 'declined' | null = null) => {
      abort.current?.()
      clear([])
      frames.forEach(consume)
      setSettled(settledAs)
      setStatus('done')
    },
    [clear, consume],
  )

  const answer = useCallback(
    async (approve: boolean) => {
      if (!question) return
      setAnswering(true)
      try {
        const outcome = await answerDecision(question.decisionId, approve)
        // Three outcomes now, not two. `pending` means this desk signed and the change is
        // waiting on the others, so the question goes but nothing has been applied.
        setSignatures(
          outcome.signed || outcome.outstanding
            ? { signed: outcome.signed ?? [], outstanding: outcome.outstanding ?? [] }
            : null,
        )
        setSettled(outcome.state === 'pending' ? null : outcome.state)
        setQuestion(null)
        setApplied(
          outcome.state === 'approved' && outcome.mpn
            ? `${outcome.refdes?.toUpperCase()} is ${outcome.mpn}${
                outcome.revision ? ` · ${outcome.revision}` : ''
              }`
            : null,
        )
        if (outcome.state === 'approved') onApplied?.()
      } catch (caught) {
        // The server's own sentence. A 403 here names the desk that owns the decision,
        // which is the only useful thing it could say.
        setError(
          caught instanceof ApiError
            ? (caught.message ?? 'That decision could not be answered.')
            : 'That decision could not be answered.',
        )
      } finally {
        setAnswering(false)
      }
    },
    [onApplied, question],
  )

  return {
    status,
    trace,
    positions,
    trying,
    proposal,
    conditional,
    reason,
    question,
    settled,
    signatures,
    applied,
    answering,
    error,
    start,
    hydrate,
    answer,
  }
}

import type { ReviewFrame } from '../lib/api'

/** One product line's lane, and the pure decisions that build it.
 *
 * Lifted out of `ReviewLanes.tsx` on 11 September so that a **hydrated lane and a live one
 * are the same object built by the same function**. The company view could not replay a
 * finished review: lane state was component state, so leaving `/changes` abandoned the run
 * and returning showed the stored documents where the trace had been. The fix is a reducer,
 * and a reducer that only the live path used would be a second definition of the same thing
 * waiting to drift from the first.
 */

export type LaneCheck = Pick<Extract<ReviewFrame, { type: 'check' }>,
  'rule' | 'scope' | 'status' | 'detail' | 'margin' | 'departments' | 'accepted'>
export type LaneTraceItem = { kind: 'said'; text: string } | ({ kind: 'check' } & LaneCheck)

export type Lane = {
  lineId: string
  name: string
  /** Everything this board's run said, in stream order. The expansion is evidence, so
   * candidate A and its verdict must not be separated by candidate B's narration. */
  trace: LaneTraceItem[]
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

export function fresh(lineId: string, name: string): Lane {
  return {
    lineId,
    name,
    trace: [],
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

/** The line-scoped frames that are evidence rather than control flow. `ReviewLanes` used to
 * drop both, so the company view stated three outcomes without showing how any was reached. */
export function withReviewFrame(
  lane: Lane,
  frame: Extract<ReviewFrame, { type: 'candidate' | 'check' }>,
): Lane {
  if (frame.type === 'candidate') {
    return { ...lane, trace: [...lane.trace, { kind: 'said', text: `Trying ${frame.part.mpn}.` }] }
  }
  return {
    ...lane,
    trace: [...lane.trace, {
      kind: 'check',
      rule: frame.rule,
      scope: frame.scope,
      status: frame.status,
      detail: frame.detail,
      margin: frame.margin,
      departments: frame.departments,
      accepted: frame.accepted,
    }],
  }
}

/** What the company view holds while a review runs, or after one has been read back. */
export type LaneState = { lanes: Lane[]; preamble: string[] }

export const emptyLanes: LaneState = { lanes: [], preamble: [] }

/**
 * One frame, applied to the whole board's worth of lanes.
 *
 * **The only place a review frame becomes lane state.** The live stream and a hydrated
 * replay both come through here, so a stored review and a running one cannot come to mean
 * different things on the way to the screen. `ReviewLanes` used to do this inline in its
 * stream callback, which is why nothing else could do it at all.
 */
export function reduceFrame(state: LaneState, frame: ReviewFrame): LaneState {
  const patch = (lineId: string, change: Partial<Lane>): LaneState => ({
    ...state,
    lanes: state.lanes.map((lane) => (lane.lineId === lineId ? { ...lane, ...change } : lane)),
  })
  const trace = (
    lineId: string,
    item: LaneTraceItem | Extract<ReviewFrame, { type: 'candidate' | 'check' }>,
  ): LaneState => ({
    ...state,
    lanes: state.lanes.map((lane) =>
      lane.lineId === lineId
        ? 'kind' in item
          ? { ...lane, trace: [...lane.trace, item] }
          : withReviewFrame(lane, item)
        : lane,
    ),
  })

  switch (frame.type) {
    case 'review_started':
      return { ...state, lanes: frame.lines.map((line) => fresh(line.line_id, line.name)) }
    case 'reasoning':
      // Discovery is said once for every board, so it arrives with no line to file it under.
      return frame.line_id
        ? trace(frame.line_id, { kind: 'said', text: frame.text })
        : { ...state, preamble: [...state.preamble, frame.text] }
    case 'candidate':
    case 'check':
      return trace(frame.line_id, frame)
    case 'question':
      return patch(frame.line_id, {
        question: {
          decisionId: frame.question_id.replace(/^decision:/, ''),
          text: frame.text,
          roles: frame.roles,
        },
      })
    case 'line_done':
      return patch(frame.line_id, {
        running: false,
        proposal: frame.proposal,
        conditional: frame.conditional,
        reason: frame.reason,
      })
    case 'error':
      return frame.line_id
        ? patch(frame.line_id, { error: frame.message, running: false })
        : state
    default:
      return state
  }
}

/** One decision a notice produced, as `GET /notices/{id}/reviews` reports it. */
export type StoredNoticeReview = {
  decision_id: string
  line_id: string
  line_name: string | null
  state: 'pending' | 'approved' | 'declined'
  proposal: string | null
  gate_rule: string | null
  roles: string[]
  signed: string[]
  outstanding: string[]
  frames: ReviewFrame[]
}

/**
 * A finished review, read back through the same reducer a live one uses.
 *
 * Lanes start `running: false` — the run is over, and every stored trace ends in `line_done`
 * which would say so anyway. **Signatures are the one thing that is not a frame**, because
 * the live path learns them from the answer to a signing call rather than from the stream,
 * so they are applied afterwards: a decision three desks have signed and one has not is not
 * the same screen as one nobody has looked at, and the replay has to say so.
 */
export function lanesFromReview(rows: readonly StoredNoticeReview[]): LaneState {
  let state: LaneState = {
    ...emptyLanes,
    lanes: rows.map((row) => ({
      ...fresh(row.line_id, row.line_name ?? 'this product line'),
      running: false,
    })),
  }
  // **The notice is stated once, the boards are stated each.** `frames_from` marks the
  // frames that belong to a board and leaves the two opening lines unmarked, because the
  // part is retired on every board and the live run says that above the lanes rather than
  // three times inside them. So the unmarked frames are read from the first decision only —
  // every decision repeats them — and the marked ones fall into the lane they name.
  rows.forEach((row, index) => {
    for (const frame of row.frames) {
      const scoped = 'line_id' in frame ? frame.line_id : null
      if (index > 0 && !scoped) continue
      state = reduceFrame(state, frame)
    }
  })
  const byLine = new Map(rows.map((row) => [row.line_id, row]))
  return {
    ...state,
    lanes: state.lanes.map((lane) => {
      const row = byLine.get(lane.lineId)
      if (!row || row.signed.length === 0) return lane
      return { ...lane, signatures: { signed: row.signed, outstanding: row.outstanding } }
    }),
  }
}

import { RequestCard } from './RequestCard'
import type { ChangeRequest } from '../lib/api'

/**
 * One board's change request, beside the run that produced it.
 *
 * **The document is about one product, so it gets its own pane.** It used to be stacked under
 * the lane that produced it, which meant the third product's request was a scroll below the
 * first and a reader comparing two of them lost the trace they came from. Here it is a column
 * that swaps when a row is opened, and the run stays on screen beside it.
 *
 * **With nothing opened there is nothing here, and that is the decision rather than an
 * oversight.** This pane used to carry the round trips a change did not have to cross, drawn
 * as two timelines. The figure was the change's rather than any board's, because the same four
 * desks sign all three products, so it repeated verbatim whichever board was open, and it is
 * the one number on this page that is an estimate rather than a measurement. It is spoken
 * instead: the constants, their sources and the arithmetic are in DEMO-DAY.md and in
 * `change.py` beside them, which is where a question about them is answered from.
 */
export function RequestPanel({ request }: { request: ChangeRequest | null }) {
  if (!request) {
    return (
      <div className="space-y-md">
        <p className="m-0 font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          The change request
        </p>
        <p className="m-0 font-data-tabular text-[13px] text-on-surface-variant leading-relaxed">
          Open a product line to read its change request. It carries the proposal, every
          candidate that was rejected with the checks that rejected it, what each of the four
          desks found, the evidence the decision rests on, what could not be checked, and the
          board as KiCad places the substitute on it.
        </p>
      </div>
    )
  }

  return <RequestCard request={request} />
}

import { RequestCard } from './RequestCard'
import { RoundTrips } from './RoundTrips'
import type { ChangeRequest } from '../lib/api'

/**
 * One board's change request, beside the run that produced it.
 *
 * **The document is about one product, so it gets its own pane.** It used to be stacked under
 * the lane that produced it, which meant the third product's request was a scroll below the
 * first and a reader comparing two of them lost the trace they came from. Here it is a column
 * that swaps when a row is opened, and the run stays on screen beside it.
 *
 * **With nothing opened it carries the change's own figure.** The round trips a change did
 * not have to cross belong to the change rather than to a board, because the same four desks
 * sign all three products, so the pane shows them once here and the documents do not repeat
 * them. The constants behind them are not on screen: the sentence naming the papers is in the
 * Q&A, and the arithmetic is in `change.py` beside the numbers.
 */
export function RequestPanel({
  request,
  requests,
  running = false,
}: {
  request: ChangeRequest | null
  /** Every request in this review, for the change-level figure when nothing is opened. */
  requests: readonly ChangeRequest[]
  /** A review is arriving. Everything this pane can show is the *last* run's answer until it
   *  is false, so it says so rather than putting yesterday's figure beside today's trace. */
  running?: boolean
}) {
  const saving = requests.find((row) => row.saving)?.saving ?? null

  if (running) {
    return (
      <div className="space-y-md">
        <p className="m-0 font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          The change request
        </p>
        <p className="m-0 font-data-tabular text-[13px] text-on-surface-variant leading-relaxed">
          Waiting for the run to finish. The documents here belong to the last one, and this
          pane is the answer rather than the working.
        </p>
      </div>
    )
  }

  if (!request) {
    return (
      <div className="space-y-md">
        <p className="m-0 font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          The change request
        </p>
        {saving ? <RoundTrips saving={saving} /> : null}
      </div>
    )
  }

  return <RequestCard request={request} />
}

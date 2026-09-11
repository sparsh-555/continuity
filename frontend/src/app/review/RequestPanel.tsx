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
 * **With nothing opened it says what the whole change was worth.** That figure is the
 * change's, not a board's: the same four desks sign all three products, so the crossings this
 * change did not have to make are the same number on every one of them. It is printed once,
 * here, and the pane says why rather than leaving a reader to notice the repetition.
 */
export function RequestPanel({
  request,
  requests,
}: {
  /** The board on screen, or null for the change as a whole. */
  request: ChangeRequest | null
  /** Every request in this review, for the change-level figure when nothing is opened. */
  requests: readonly ChangeRequest[]
}) {
  const saving = requests.find((row) => row.saving)?.saving ?? null

  if (!request) {
    return (
      <div className="space-y-md">
        <p className="m-0 font-data-tabular text-[12px] tracking-[0.08em] text-on-surface-variant uppercase">
          The change
        </p>
        {saving ? (
          <RoundTrips saving={saving} />
        ) : (
          <p className="m-0 font-data-tabular text-[13px] text-on-surface-variant leading-relaxed">
            Open a product line to read its change request.
          </p>
        )}
        <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant/70 leading-relaxed">
          The round trips are the change&rsquo;s rather than any one board&rsquo;s: the same
          desks sign all {requests.length} of these products, so none of them crosses a handoff
          the others do not. What differs by board is its own cost and whether the substitute
          fits the design that exists, and both are on that board&rsquo;s own change request.
        </p>
      </div>
    )
  }

  return <RequestCard request={request} />
}

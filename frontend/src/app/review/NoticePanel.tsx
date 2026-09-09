import type { LineNotice, LineRequest } from '../lib/api'
import { SidePanel } from './SidePanel'

/**
 * What is coming for this product, where a conflict would be.
 *
 * The notice was briefly a banner across the top of the page and then a block at the head of
 * the trace. Both were wrong for the same reason: it is this board's conflict, and this
 * application already has a place for a board's conflict — the drawer on the right that
 * `design/ConflictPanel` opens into. **REVIEW THIS LINE** is here because this is the panel
 * that states the problem, and starting the work belongs beside the statement of it.
 */
export function NoticePanel({
  notices,
  requests,
  running,
  reviewed,
  onStart,
  onOpenRequest,
  onClose,
}: {
  notices: LineNotice[]
  requests: LineRequest[]
  /** A run is in flight, so starting another would abandon it. */
  running: boolean
  /** This session has already produced a trace, so the button offers to run it again. */
  reviewed: boolean
  onStart: (notice: LineNotice) => void
  onOpenRequest: (request: LineRequest) => void
  onClose: () => void
}) {
  return (
    <SidePanel
      onClose={onClose}
      title={notices.length === 1 ? 'END OF LIFE' : `END OF LIFE · ${notices.length}`}
      tone="error"
    >
      <div className="p-md space-y-md">
        {notices.map((notice) => {
          const answered = requests.filter((request) => request.notice_id === notice.id)
          return (
            <article
              className="border border-error/60 bg-error-container/10 rounded p-md space-y-md"
              key={notice.id}
            >
              <div className="space-y-1">
                <p className="font-data-tabular text-[12px] text-error leading-relaxed">
                  {notice.mpn} at {notice.refdes.join(', ').toUpperCase()}
                </p>
                <p className="font-data-tabular text-[11px] text-on-surface leading-relaxed">
                  {notice.manufacturer ?? 'Manufacturer not stated'}
                  {notice.effective_date ? ` · last order ${notice.effective_date}` : ''}
                </p>
                {notice.replacement_mpn ? (
                  <p className="font-data-tabular text-[11px] text-on-surface-variant leading-relaxed">
                    Recommends {notice.replacement_mpn}
                  </p>
                ) : null}
                {notice.reason ? (
                  <p className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
                    {notice.reason}
                  </p>
                ) : null}
              </div>

              <button
                className="h-8 w-full px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
                disabled={running}
                onClick={() => onStart(notice)}
                type="button"
              >
                {running ? 'RUNNING…' : reviewed ? 'REVIEW AGAIN' : 'REVIEW THIS LINE'}
              </button>

              {/* What this board already decided about this notice, opening in place rather
                  than navigating to the company-wide page. The reasoning that produced a
                  substitution belongs on the product it changed. */}
              {answered.map((request) => (
                <button
                  className="w-full text-left border-t border-outline-variant pt-sm hover:bg-surface-variant/40 transition-colors rounded px-1"
                  key={request.id}
                  onClick={() => onOpenRequest(request)}
                  type="button"
                >
                  <span className="font-data-tabular text-[10px] text-on-surface-variant uppercase">
                    Already answered
                  </span>
                  <span className="block font-data-tabular text-[11px] text-on-surface">
                    {request.proposal ?? 'no viable part'}
                    <span className="text-on-surface-variant">
                      {' · '}
                      {new Date(request.created_at).toLocaleDateString()}
                    </span>
                  </span>
                </button>
              ))}
            </article>
          )
        })}
      </div>
    </SidePanel>
  )
}

import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { ReviewLanes } from '../review/ReviewLanes'
import { WaitingOnYou } from '../review/WaitingOnYou'
import { Page } from '../shell/Page'
import { useNoticeArrivals } from '../hooks/useNoticeArrivals'
import {
  ApiError,
  exposureTo,
  listChangeRequests,
  listNotices,
  listWaitingDecisions,
  receiveNotice,
  type AffectedLine,
  type ChangeRequest,
  type Notice,
  type ReceivedNotice,
  type WaitingDecision,
} from '../lib/api'

export function skippedFor(notice: Notice | null): Notice['review_skipped'] {
  return notice?.review_skipped ?? []
}

/** The two facts that distinguish notices which retire the same manufacturer part.
 *
 * A notice's own reference number is the thing that tells two of them apart, and the date it
 * arrived is the fallback for one that carries no number — which preliminary notices often do.
 *
 * The date is rendered in the reader's own timezone, the way `NoticePanel` already renders a
 * stored timestamp. It used to be `created_at.slice(0, 10)`, which is a UTC truncation: for
 * anybody east of Greenwich a notice received at nine in the morning shows yesterday's date,
 * and a date that can be a day wrong is worse than no date on the one row whose whole job is
 * telling two same-part notices apart.
 */
export function noticeIdentity(notice: Notice): string {
  const received = new Date(notice.created_at).toLocaleDateString()
  return notice.reference ? `${notice.reference} · received ${received}` : `received ${received}`
}

export default function ChangesRoute() {
  const { arrival } = useNoticeArrivals()
  const navigate = useNavigate()
  const [notices, setNotices] = useState<Notice[]>([])
  const [selected, setSelected] = useState<Notice | null>(null)
  const [received, setReceived] = useState<ReceivedNotice | null>(null)
  const [requests, setRequests] = useState<ChangeRequest[]>([])
  const [skipped, setSkipped] = useState<Notice['review_skipped']>([])
  const [affected, setAffected] = useState<AffectedLine[] | null>(null)
  const [waiting, setWaiting] = useState<WaitingDecision[]>([])
  const [candidates, setCandidates] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setNotices(await listNotices())
    } catch {
      setError('Could not load the notices received so far.')
    }
  }, [])

  // **What this desk owes, asked for on the page rather than on a page of its own.** The
  // rail badge already counts it; this is the same question answered where the change is, so
  // the reader who has to sign something does not have to go and find it first.
  const refreshWaiting = useCallback(async () => {
    try {
      setWaiting(await listWaitingDecisions())
    } catch {
      // A queue that cannot be read is not worth a banner over a review that can.
      setWaiting([])
    }
  }, [])

  useEffect(() => {
    if (!busy) void refresh()
  }, [arrival, busy, refresh])

  useEffect(() => {
    void refreshWaiting()
  }, [refreshWaiting, selected, requests])

  const upload = useCallback(
    async (file: File) => {
      setBusy(true)
      setError(null)
      setRequests([])
      // Both, and for the same reason: what was not checked was not checked *for the
      // notice that was on screen*. Carried across, it reads as a finding about the new
      // one, and names a candidate excluded from a review that has not been run yet.
      setSkipped([])
      try {
        const bytes = new Uint8Array(await file.arrayBuffer())
        let binary = ''
        bytes.forEach((byte) => {
          binary += String.fromCharCode(byte)
        })
        const next = await receiveNotice(btoa(binary), file.name)
        setReceived(next)
        setSelected(null)
        await refresh()
      } catch (caught) {
        // The server's own sentence when it has one. A 422 here says something specific —
        // nothing in the document could be read as a notice — and replacing that with
        // "something went wrong" throws away the only actionable part.
        setError(
          caught instanceof ApiError && caught.status === 422
            ? 'Nothing in that document could be read as a change notice: no part number backed by a line of the document itself.'
            : 'That notice could not be read.',
        )
      } finally {
        setBusy(false)
      }
    },
    [refresh],
  )

  const open = useCallback(async (notice: Notice) => {
    setSelected(notice)
    setReceived(null)
    setError(null)
    setSkipped(skippedFor(notice))
    setAffected(null)
    try {
      setRequests(await listChangeRequests(notice.id))
    } catch {
      setRequests([])
    }
    // Asked for rather than assumed. A notice that arrived by email carries no upload
    // reply, and "affects three product lines" is the sentence this screen turns on.
    try {
      setAffected(await exposureTo(notice.mpn))
    } catch {
      setAffected(null)
    }
  }, [])

  /** The same read, without touching anything else on the page.
   *
   * `RUN IT AGAIN` writes new change requests over the old ones, and the ones on screen were
   * read before it started. Re-reading them through `open` would clear the notice, drop the
   * selection and put the page back to the beginning under a run in progress. */
  const reloadRequests = useCallback(async (noticeId: string) => {
    try {
      setRequests(await listChangeRequests(noticeId))
    } catch {
      // The old documents stay up. They are stale rather than wrong for this notice, and a
      // failed refresh is not a reason to blank the page.
    }
  }, [])

  // Whatever arrived most recently, already open — or the one the caller named. A mailed
  // notice used to land as an unselected ten-pixel chip beside copy reading "Receive a
  // change notice to begin", which is false once one has been received and is why the
  // review looked missing. Arriving from a product line's banner was worse: it navigated
  // here about a specific notice and then selected none of them.
  const wanted = new URLSearchParams(useLocation().search).get('notice')
  useEffect(() => {
    if (notices.length === 0) return
    if (selected || received) return
    void open(notices.find((notice) => notice.id === wanted) ?? notices[0])
  }, [notices, open, received, selected, wanted])

  const active = received?.notice ?? selected
  const reaches = received?.affected ?? affected
  return (
    <Page
      actions={
        <label className="font-data-tabular text-[12px] text-primary-container border border-primary-container rounded px-md py-1 cursor-pointer hover:bg-surface-variant transition-colors">
          {/* Reading a notice is a model call against a PDF and takes a few seconds. A
              button that looks inert for that long reads as a button that did nothing. */}
          {busy ? 'READING…' : 'UPLOAD ONE INSTEAD'}
          <input
            accept=".pdf,.txt,text/plain,application/pdf"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void upload(file)
              event.target.value = ''
            }}
            type="file"
          />
        </label>
      }
      fill
      subtitle={
        active ? (
          <>
            {active.manufacturer ?? 'manufacturer not stated'}
            {/* A notice that has just been uploaded has not been stored yet, so it carries no
                reference and no arrival time to identify it by. Printed empty rather than
                invented, which is the same rule the notice list follows. */}
            {'id' in active ? ` · ${noticeIdentity(active)}` : ''}
            {active.replacement_mpn ? ` · recommends ${active.replacement_mpn}` : ''}
          </>
        ) : undefined
      }
      title="CHANGES"
    >
      <WaitingOnYou
        decisions={waiting}
        onOpen={(noticeId) => navigate(`/changes?notice=${encodeURIComponent(noticeId)}`)}
      />

      {/* **Two panes with a fixed height each, rather than one column that grows.** The page
          is locked to the viewport now, so the notice stays where it is while the review
          beside it runs, and a trace that fills the right pane scrolls inside it. Laid out
          as a scrolling page, opening a lane pushed the notice that raised it off the top of
          the screen, which is the one thing the reader wants to keep in view. */}
      <div className="flex gap-lg items-stretch flex-1 min-h-0">
        <aside className="w-[380px] flex-shrink-0 h-full overflow-y-auto space-y-md pr-sm">
          {/* A list, not a row of ten-pixel chips. What arrived, when, how, and what it
              retires — enough to pick one without having already known which to pick. The
              old shape was a button that did not look like a button, holding the only route
              to the review. */}
          {notices.length > 0 ? (
            <div className="flex flex-col gap-1">
              {notices.map((notice) => {
                const open_ = (selected?.id ?? received?.id) === notice.id
                return (
                  <button
                    className={`text-left border rounded px-md py-sm transition-colors ${
                      open_
                        ? 'border-primary-container bg-surface-container-low'
                        : 'border-outline-variant hover:border-on-surface-variant'
                    }`}
                    key={notice.id}
                    onClick={() => void open(notice)}
                    type="button"
                  >
                    <span className="flex items-baseline justify-between gap-md">
                      <span
                        className={`font-data-tabular text-[14px] ${
                          open_ ? 'text-primary-container' : 'text-on-surface'
                        }`}
                      >
                        {notice.mpn}
                      </span>
                      <span className="font-data-tabular text-[11px] text-outline shrink-0">
                        {notice.source}
                      </span>
                    </span>
                    <span className="block font-data-tabular text-[11px] text-on-surface-variant mt-0.5">
                      {noticeIdentity(notice)}
                    </span>
                    <span className="block font-data-tabular text-[11px] text-on-surface-variant mt-0.5">
                      {notice.manufacturer ?? 'manufacturer not stated'}
                      {notice.effective_date ? ` · last order ${notice.effective_date}` : ''}
                      {notice.replacement_mpn ? ` · recommends ${notice.replacement_mpn}` : ''}
                    </span>
                  </button>
                )
              })}
            </div>
          ) : null}

          {error ? <p className="font-data-tabular text-[12px] text-error">{error}</p> : null}

          {active ? (
            <section className="border border-outline-variant rounded p-lg space-y-sm">
              <h2 className="font-data-tabular text-[16px] text-on-surface">{active.mpn}</h2>
              {/* The line the part number was actually read from. A notice whose MPN cannot
                  be traced back into its own document would start a review of a part nobody
                  sells. */}
              <p className="font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                read from: “{active.mpn_line}”
              </p>

              {reaches ? (
                <p className="font-body-md text-[14px] text-on-surface leading-relaxed">
                  {reaches.length === 0
                    ? 'This part is not on any product line you ship.'
                    : `Affects ${reaches.length} product line${reaches.length === 1 ? '' : 's'}: ${reaches.map((line) => line.name).join(', ')}.`}
                </p>
              ) : null}

              {/* The candidates are found, not typed: the notice's own recommendation, then
                  the approved list, then the distributor's catalogue. This box is an override
                  for a part somebody wants tried anyway, and it is deliberately not the way in. */}
              <details className="pt-sm">
                <summary className="font-data-tabular text-[11px] text-on-surface-variant cursor-pointer">
                  TRY A PARTICULAR PART TOO
                </summary>
                <input
                  className="input-field px-sm h-8 w-full mt-1 font-data-tabular text-[12px]"
                  onChange={(event) => setCandidates(event.target.value)}
                  placeholder="MPN, MPN"
                  value={candidates}
                />
              </details>
            </section>
          ) : null}

          {skipped.length > 0 ? (
            <section className="space-y-1">
              <h2 className="font-data-tabular text-[12px] text-tertiary-container">NOT CHECKED</h2>
              {skipped.map(({ mpn, reason }) => (
                <p key={mpn} className="font-data-tabular text-[12px] text-tertiary-container">
                  {mpn}: {reason}, so it was not checked.
                </p>
              ))}
            </section>
          ) : null}
        </aside>

        <div className="flex-1 min-w-0 h-full overflow-y-auto pr-sm">
          {active && (received?.id ?? selected?.id) ? (
            <ReviewLanes
              candidates={candidates
                .split(/[,\n]/)
                .map((mpn) => mpn.trim())
                .filter(Boolean)}
              noticeId={(received?.id ?? selected?.id) as string}
              onApplied={() => {
                void refresh()
                void refreshWaiting()
              }}
              onFinished={() => {
                void reloadRequests((received?.id ?? selected?.id) as string)
                void refreshWaiting()
              }}
              requests={requests}
            />
          ) : (
            <p className="font-body-md text-[14px] text-on-surface-variant leading-relaxed">
              Nothing has arrived yet. Forward a change notice to the mailbox, or upload one.
              Continuity reads the part number out of the document, finds the products that
              carry it, and checks every substitute against each product’s own operating
              conditions.
            </p>
          )}
        </div>
      </div>
    </Page>
  )
}

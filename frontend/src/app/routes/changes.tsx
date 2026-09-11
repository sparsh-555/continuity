import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router'

import { ReviewLanes } from '../review/ReviewLanes'
import { Page } from '../shell/Page'
import { useNoticeArrivals } from '../hooks/useNoticeArrivals'
import { matrixQuery } from './matrixLink'
import {
  ApiError,
  exposureTo,
  listChangeRequests,
  listNotices,
  receiveNotice,
  type AffectedLine,
  type ChangeRequest,
  type Notice,
  type ReceivedNotice,
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
  const [notices, setNotices] = useState<Notice[]>([])
  const [selected, setSelected] = useState<Notice | null>(null)
  const [received, setReceived] = useState<ReceivedNotice | null>(null)
  const [requests, setRequests] = useState<ChangeRequest[]>([])
  const [skipped, setSkipped] = useState<Notice['review_skipped']>([])
  const [affected, setAffected] = useState<AffectedLine[] | null>(null)
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

  useEffect(() => {
    if (!busy) void refresh()
  }, [arrival, busy, refresh])

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
  // Everything the review tried on these boards: the part going away, every proposal, and
  // every alternative it ruled out. The losers are the reason to open the matrix at all.
  const working = useMemo(
    () =>
      reaches && requests.length
        ? matrixQuery({
            affected: reaches,
            candidates: [
              { mpn: active?.mpn ?? '' },
              ...requests.flatMap((request) => [
                { mpn: request.proposal ?? '' },
                ...request.alternatives.map((alternative) => ({
                  mpn: alternative.mpn,
                  manufacturer: alternative.manufacturer,
                })),
              ]),
            ],
          })
        : null,
    [active, reaches, requests],
  )

  return (
    <Page
      actions={
        <label className="font-data-tabular text-[11px] text-primary-container border border-primary-container rounded px-md py-1 cursor-pointer hover:bg-surface-variant transition-colors">
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
      title="CHANGES"
      width="wide"
    >
      {/* **Master and detail, rather than three screens down one column.** The left is what
          arrived and what it reaches; the right is one thing at a time — the run, the lanes,
          and the change request each lane ends in. A reading column made a finished document
          arrive in the same place as a running one, which read as a replacement for it, and
          put the third product's request a scroll below the first. See R3. */}
      <div className="flex gap-lg items-start">
        <aside className="w-[340px] flex-shrink-0 space-y-md">

      {/* A list, not a row of ten-pixel chips. What arrived, when, how, and what it
          retires — enough to pick one without having already known which to pick. The old
          shape was a button that did not look like a button, holding the only route to
          the review. */}
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
                    className={`font-data-tabular text-data-tabular ${
                      open_ ? 'text-primary-container' : 'text-on-surface'
                    }`}
                  >
                    {notice.mpn}
                  </span>
                  <span className="font-data-tabular text-[10px] text-outline shrink-0">
                    {notice.source}
                  </span>
                </span>
                <span className="block font-data-tabular text-[10px] text-on-surface-variant mt-0.5">
                  {noticeIdentity(notice)}
                </span>
                <span className="block font-data-tabular text-[10px] text-on-surface-variant mt-0.5">
                  {notice.manufacturer ?? 'manufacturer not stated'}
                  {notice.effective_date ? ` · last order ${notice.effective_date}` : ''}
                  {notice.replacement_mpn ? ` · recommends ${notice.replacement_mpn}` : ''}
                </span>
              </button>
            )
          })}
        </div>
      ) : null}

      {error ? <p className="font-data-tabular text-[11px] text-error">{error}</p> : null}

      {active ? (
        <section className="border border-outline-variant rounded p-lg space-y-sm">
          <h2 className="font-headline-sm text-headline-sm text-on-surface">{active.mpn}</h2>
          <p className="font-data-tabular text-[11px] text-on-surface-variant">
            {active.manufacturer ?? 'manufacturer not stated'}
            {active.effective_date ? ` · last order ${active.effective_date}` : ''}
            {active.replacement_mpn ? ` · recommends ${active.replacement_mpn}` : ''}
          </p>
          {/* The line the part number was actually read from. A notice whose MPN cannot be
              traced back into its own document would start a review of a part nobody sells. */}
          <p className="font-data-tabular text-[10px] text-on-surface-variant/70">
            read from: “{active.mpn_line}”
          </p>

          {reaches ? (
            <p className="font-data-tabular text-[11px] text-on-surface">
              {reaches.length === 0
                ? 'This part is not on any product line you ship.'
                : `Affects ${reaches.length} product line${reaches.length === 1 ? '' : 's'}: ${reaches.map((line) => line.name).join(', ')}.`}
            </p>
          ) : null}

          {/* The candidates are found, not typed: the notice's own recommendation, then
              the approved list, then the distributor's catalogue. This box is an override
              for a part somebody wants tried anyway, and it is deliberately not the way in. */}
          <details className="pt-sm">
            <summary className="font-data-tabular text-[10px] text-on-surface-variant cursor-pointer">
              TRY A PARTICULAR PART TOO
            </summary>
            <input
              className="input-field px-sm h-8 w-full max-w-[420px] mt-1 font-data-tabular text-[11px]"
              onChange={(event) => setCandidates(event.target.value)}
              placeholder="MPN, MPN"
              value={candidates}
            />
          </details>
        </section>
      ) : null}

      {skipped.length > 0 ? (
        <section className="space-y-1">
          <h2 className="font-data-tabular text-[11px] text-tertiary-container">
            NOT CHECKED
          </h2>
          {skipped.map(({ mpn, reason }) => (
            <p key={mpn} className="font-data-tabular text-[10px] text-tertiary-container">
              {mpn}: {reason}, so it was not checked.
            </p>
          ))}
        </section>
      ) : null}
        </aside>

        <div className="flex-1 min-w-0 space-y-md">

          {active && (received?.id ?? selected?.id) ? (
            <>
              <ReviewLanes
                candidates={candidates
                  .split(/[,\n]/)
                  .map((mpn) => mpn.trim())
                  .filter(Boolean)}
                noticeId={(received?.id ?? selected?.id) as string}
                onApplied={() => void refresh()}
                requests={requests}
              />
              {/* The grid these were cut from, with every rejection's working and every
                  department's name on it. It carries the boards, the position and the parts
                  that were tried, because the review already knows all three and the matrix
                  used to ask the reader to type them back in. Rendered only when there is
                  something to open it on, and **below the change requests** — which is where
                  `RUNNER.md` sends the presenter looking for it. */}
              {working ? (
                <div className="flex justify-end">
                  <Link
                    className="font-data-tabular text-[10px] text-primary-container hover:underline"
                    to={`/matrix?${working.search}`}
                  >
                    SHOW THE WORKING · {working.lines} BOARD
                    {working.lines === 1 ? '' : 'S'} AT {working.slot.toUpperCase()} →
                  </Link>
                </div>
              ) : null}
            </>
          ) : (
            <p className="font-data-tabular text-[11px] text-on-surface-variant">
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

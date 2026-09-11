import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router'

import { Modal } from '../design/Modal'
import { RequestPanel } from '../review/RequestPanel'
import { ReviewLanes } from '../review/ReviewLanes'
import { WaitingOnYou } from '../review/WaitingOnYou'
import { Page } from '../shell/Page'
import { useNoticeArrivals } from '../hooks/useNoticeArrivals'
import {
  ApiError,
  answerDecision,
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

/**
 * The page a change notice is answered on, in three panes.
 *
 * **The desk, the run, and the document.** The left pane is what this reader owes and where a
 * signature happens; the middle is the run, three boards advancing together; the right is one
 * board's change request, which is the object the whole product exists to produce. The design
 * workspace is laid out the same way, and for the same reason: the three things a person is
 * holding at once should be three things on screen rather than a scroll apart.
 *
 * **The notice is stated once, at the top of the left pane.** What is retiring and what the
 * notice recommends are true of every affected product, and the run says them above the lanes
 * rather than three times inside them.
 */
export default function ChangesRoute() {
  const { arrival } = useNoticeArrivals()

  const [notices, setNotices] = useState<Notice[]>([])
  const [selected, setSelected] = useState<Notice | null>(null)
  const [received, setReceived] = useState<ReceivedNotice | null>(null)
  const [requests, setRequests] = useState<ChangeRequest[]>([])
  const [skipped, setSkipped] = useState<Notice['review_skipped']>([])
  const [affected, setAffected] = useState<AffectedLine[] | null>(null)
  const [waiting, setWaiting] = useState<WaitingDecision[]>([])
  const [candidates, setCandidates] = useState('')
  const [candidateOpen, setCandidateOpen] = useState(false)
  /** Which board's change request is on the right. One at a time, so the pane has an owner. */
  const [openLineId, setOpenLineId] = useState<string | null>(null)
  /** A signature the server refused, by decision. About the desk, never about the board. */
  const [refusals, setRefusals] = useState<Record<string, string>>({})
  const [signing, setSigning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setNotices(await listNotices())
    } catch {
      setError('Could not load the notices received so far.')
    }
  }, [])

  /** What this desk owes, asked for where the change is rather than on a page of its own. */
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
    setOpenLineId(null)
    setRefusals({})
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

  /** The same read, without touching anything else on the page. */
  const reloadRequests = useCallback(async (noticeId: string) => {
    try {
      setRequests(await listChangeRequests(noticeId))
    } catch {
      // The old documents stay up. They are stale rather than wrong for this notice, and a
      // failed refresh is not a reason to blank the page.
    }
  }, [])

  /** Sign or refuse, from the pane that is about this desk.
   *
   * **The refusal goes beside the buttons and never onto the board.** A 403 here means this
   * desk cannot sign this decision, which is a fact about the desk; painting the lane FAILED
   * over it would say the board failed a check it passed.
   */
  const answer = useCallback(
    async (decision: WaitingDecision, approve: boolean) => {
      setSigning(decision.id)
      setRefusals((current) => ({ ...current, [decision.id]: '' }))
      try {
        await answerDecision(decision.id, approve)
        await refreshWaiting()
        const noticeId = received?.id ?? selected?.id
        if (noticeId) await reloadRequests(noticeId)
      } catch (caught) {
        setRefusals((current) => ({
          ...current,
          [decision.id]:
            caught instanceof ApiError
              ? (caught.message ?? 'That decision could not be answered.')
              : 'That decision could not be answered.',
        }))
      } finally {
        setSigning(null)
      }
    },
    [received?.id, reloadRequests, refreshWaiting, selected?.id],
  )

  // Whatever arrived most recently, already open, or the one the caller named.
  const wanted = new URLSearchParams(useLocation().search).get('notice')
  useEffect(() => {
    if (notices.length === 0) return
    if (selected || received) return
    void open(notices.find((notice) => notice.id === wanted) ?? notices[0])
  }, [notices, open, received, selected, wanted])

  const active = received?.notice ?? selected
  const reaches = received?.affected ?? affected
  const openRequest = requests.find((row) => row.line_id === openLineId) ?? null

  return (
    <Page
      actions={
        <div className="flex items-center gap-sm">
          {/* **Trying a part is a footnote to the review, not a step in it.** It was a
              disclosure triangle inside the notice card, which is where a reader looks for
              what the notice says rather than for what they might add. The candidates are
              found rather than typed, and this is an override for somebody who wants a
              particular part tried anyway. */}
          <button
            className="h-8 px-md border border-outline-variant rounded font-data-tabular text-[12px] text-on-surface-variant hover:border-on-surface-variant transition-colors"
            onClick={() => setCandidateOpen(true)}
            type="button"
          >
            {candidates.trim() ? `TRYING ${candidates.split(',').filter(Boolean).length} TOO` : 'TRY A PARTICULAR PART'}
          </button>
          <label className="h-8 px-md flex items-center font-data-tabular text-[12px] text-primary-container border border-primary-container rounded cursor-pointer hover:bg-surface-variant transition-colors">
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
        </div>
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
      {/* **Proportional columns with a floor each, rather than three fixed widths.** Three
          fixed widths add up to more than a laptop screen, and the middle column — the run,
          which is the thing this page is for — collapses to a sliver of wrapped text. The
          left pane holds one desk's queue and the right one holds one document, so they take
          a share of the width; the run takes what is left, and each has a minimum below which
          it stops shrinking. */}
      <div className="grid grid-cols-[minmax(300px,20%)_minmax(320px,1fr)_minmax(400px,32%)] gap-lg items-stretch flex-1 min-h-0">
        {/* ── The desk ───────────────────────────────────────────────────────────── */}
        <aside className="h-full overflow-y-auto space-y-md pr-sm">
          {/* **A heading, because a column of cards with no name is a column nobody can
              place.** The pane holds two different things, the notices and what this desk
              owes, and they were told apart only by reading them. */}
          <h2 className="m-0 font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
            Notices
          </h2>

          {/* A list, not a row of ten-pixel chips. What arrived, when, how, and what it
              retires, enough to pick one without having already known which to pick.

              **The open one carries its own detail.** The notice's own line and what it
              reaches were a second box below the list, so the selected row and the thing it
              described were two cards saying overlapping things. They are one box now: the
              row you pressed is the row that answers. */}
          {notices.length > 0 ? (
            <div className="flex flex-col gap-1">
              {notices.map((notice) => {
                const isOpen = (selected?.id ?? received?.id) === notice.id
                return (
                  <button
                    className={`text-left border rounded px-md py-sm transition-colors ${
                      isOpen
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
                          isOpen ? 'text-primary-container' : 'text-on-surface'
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
                    {isOpen && active ? (
                      <span className="block mt-sm pt-sm border-t border-outline-variant/50">
                        {/* The line the part number was actually read from. A notice whose MPN
                            cannot be traced back into its own document would start a review
                            of a part nobody sells. */}
                        <span className="block font-data-tabular text-[11px] text-on-surface-variant/70 leading-relaxed">
                          read from: “{active.mpn_line}”
                        </span>
                        {reaches ? (
                          <span className="block font-data-tabular text-[12px] text-on-surface leading-relaxed mt-0.5">
                            {reaches.length === 0
                              ? 'This part is not on any product line you ship.'
                              : `Affects ${reaches.length} product line${reaches.length === 1 ? '' : 's'}: ${reaches.map((line) => line.name).join(', ')}.`}
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          ) : null}

          {error ? <p className="font-data-tabular text-[12px] text-error">{error}</p> : null}

          {/* **The one place a change is signed.** The buttons and the four ticks used to be
              here *and* on the lane and *again* on the change request; a desk that owes a
              signature should find it where it is told it owes one. */}
          <WaitingOnYou
            busy={signing}
            decisions={waiting}
            onAnswer={(decision, approve) => void answer(decision, approve)}
            requests={requests}
          />

          {Object.entries(refusals)
            .filter(([, message]) => message)
            .map(([id, message]) => (
              <p className="font-data-tabular text-[12px] text-error leading-relaxed" key={id}>
                {message}
              </p>
            ))}

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

        {/* ── The run ────────────────────────────────────────────────────────────── */}
        <div className="min-w-0 h-full overflow-y-auto pr-sm">
          {active && (received?.id ?? selected?.id) ? (
            <ReviewLanes
              candidates={candidates
                .split(/[,\n]/)
                .map((mpn) => mpn.trim())
                .filter(Boolean)}
              noticeId={(received?.id ?? selected?.id) as string}
              onFinished={() => {
                const noticeId = received?.id ?? selected?.id
                if (noticeId) void reloadRequests(noticeId)
                void refreshWaiting()
              }}
              onOpenLine={setOpenLineId}
              openLineId={openLineId}
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

        {/* ── The document ───────────────────────────────────────────────────────── */}
        <div className="h-full overflow-y-auto pr-sm">
          <RequestPanel request={openRequest} requests={requests} />
        </div>
      </div>

      <Modal
        confirmLabel="DONE"
        onClose={() => setCandidateOpen(false)}
        onConfirm={() => setCandidateOpen(false)}
        open={candidateOpen}
        title="TRY A PARTICULAR PART TOO"
      >
        <div className="space-y-md">
          <p className="m-0 font-body-md text-[14px] text-on-surface-variant leading-relaxed">
            The candidates are found rather than typed: the notice&rsquo;s own recommendation,
            then the approved manufacturer list, then the distributor&rsquo;s catalogue in the
            same package. This is an override for a part somebody wants tried anyway, and it is
            deliberately not the way in.
          </p>
          <input
            className="input-field px-sm h-9 w-full font-data-tabular text-[13px]"
            onChange={(event) => setCandidates(event.target.value)}
            placeholder="MPN, MPN"
            value={candidates}
          />
          <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant">
            Press RUN IT AGAIN on the review for them to be tried.
          </p>
        </div>
      </Modal>
    </Page>
  )
}

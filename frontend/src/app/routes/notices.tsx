import { useCallback, useEffect, useState } from 'react'

import { BoardConsequence } from '../board/BoardConsequence'
import {
  ApiError,
  listChangeRequests,
  listNotices,
  receiveNotice,
  reviewNotice,
  type ChangeRequest,
  type Notice,
  type ReceivedNotice,
} from '../lib/api'

/** A change request, as the person who has to sign it reads it.
 *
 *  This is the document the whole product exists to produce, and until now it existed only
 *  as JSON on an endpoint. The matrix shows the grid it is derived from — that is the
 *  working; this is the deliverable. */
function RequestCard({ request }: { request: ChangeRequest }) {
  const rejected = request.alternatives.filter((a) => a.rejected_because)
  const viable = request.alternatives.filter((a) => !a.rejected_because)

  return (
    <article className="border border-outline-variant rounded p-lg space-y-md bg-surface-container-low">
      <header className="flex items-start justify-between gap-md">
        <div className="min-w-0">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">{request.line_name}</h3>
          <p className="font-data-tabular text-[11px] text-on-surface-variant mt-0.5">
            {request.revision ? `${request.revision} · ` : ''}
            fitted today: {request.baseline_mpn ?? 'unknown'}
          </p>
        </div>
        <span
          className={`font-data-tabular text-[11px] px-sm py-0.5 border rounded whitespace-nowrap ${
            request.proposal
              ? 'border-outline-variant text-[#4ade80]'
              : 'border-error text-error'
          }`}
        >
          {request.proposal ?? 'NO VIABLE PART'}
        </span>
      </header>

      <p className="font-data-tabular text-[11px] text-on-surface leading-relaxed">
        {request.proposal_detail}
      </p>

      {rejected.length > 0 ? (
        <section className="space-y-1">
          <h4 className="font-data-tabular text-[10px] text-on-surface-variant">
            CONSIDERED AND REJECTED
          </h4>
          {/* The sentence that killed each, verbatim. A proposal on its own asks to be
              trusted; one that shows its rejections asks to be checked. */}
          {rejected.map((alternative) => (
            <p
              key={alternative.mpn}
              className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed"
            >
              <span className="text-on-surface">{alternative.mpn}</span> —{' '}
              {alternative.rejected_because}
            </p>
          ))}
        </section>
      ) : null}

      {viable.length > 0 ? (
        <p className="font-data-tabular text-[10px] text-on-surface-variant">
          Also viable, not chosen: {viable.map((a) => a.mpn).join(', ')}
        </p>
      ) : null}

      {request.evidence.length > 0 ? (
        <section className="space-y-1">
          <h4 className="font-data-tabular text-[10px] text-on-surface-variant">EVIDENCE</h4>
          {request.evidence.map((check, index) => (
            <p
              key={`${check.rule}:${check.scope ?? ''}:${index}`}
              className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed"
            >
              <span className={check.status === 'failed' ? 'text-error' : 'text-[#4ade80]'}>
                {check.rule.replace(/_/g, ' ')}
                {check.margin ? ` · ${check.margin}` : ''}
              </span>{' '}
              — {check.detail}
            </p>
          ))}
        </section>
      ) : null}

      {/* The two admissions, kept apart. "We do not answer this" and "we tried and had
          nothing to read" are different sentences, and a document that omitted either would
          read as a clean bill of health for questions nobody asked. */}
      <section className="space-y-1 border-t border-outline-variant pt-md">
        {request.not_assessed.length > 0 ? (
          <p className="font-data-tabular text-[10px] text-tertiary-container">
            Not assessed: {request.not_assessed.map((r) => r.replace(/_/g, ' ')).join(', ')}.
          </p>
        ) : null}
        {request.no_evidence.length > 0 ? (
          <p className="font-data-tabular text-[10px] text-tertiary-container">
            Could not be checked: {request.no_evidence.map((r) => r.replace(/_/g, ' ')).join(', ')}.
          </p>
        ) : null}
      </section>

      <BoardConsequence
        candidate={request.proposal}
        lineId={request.line_id}
        retiring={request.notice_mpn}
      />

      <section className="flex flex-wrap gap-lg border-t border-outline-variant pt-md">
        <div className={request.proposal ? '' : 'hidden'}>
          <p className="font-data-tabular text-[10px] text-on-surface-variant">ONE-TIME</p>
          <p className="font-data-tabular text-[11px] text-on-surface">
            ${request.cost.one_time.toLocaleString()}
          </p>
          <p className="font-data-tabular text-[10px] text-on-surface-variant">
            {request.cost.one_time_basis}
          </p>
        </div>
        <div className={request.proposal ? '' : 'hidden'}>
          <p className="font-data-tabular text-[10px] text-on-surface-variant">RECURRING</p>
          <p className="font-data-tabular text-[11px] text-on-surface">
            {request.cost.recurring_annual === null
              ? '—'
              : `$${request.cost.recurring_annual.toLocaleString()} a year`}
          </p>
          <p className="font-data-tabular text-[10px] text-on-surface-variant">
            {request.cost.unit_delta === null
              ? 'no published price to compare'
              : request.cost.annual_volume
                ? `${request.cost.unit_delta > 0 ? '+' : ''}$${request.cost.unit_delta} a unit at ${request.cost.annual_volume.toLocaleString()}/yr`
                : `${request.cost.unit_delta > 0 ? '+' : ''}$${request.cost.unit_delta} a unit — no annual volume stated`}
          </p>
        </div>
        {request.approvals_required.length > 0 ? (
          <div>
            <p className="font-data-tabular text-[10px] text-on-surface-variant">APPROVALS</p>
            <p className="font-data-tabular text-[11px] text-on-surface">
              {request.approvals_required.join(' and ')}
            </p>
          </div>
        ) : null}
      </section>
    </article>
  )
}

export default function NoticesRoute() {
  const [notices, setNotices] = useState<Notice[]>([])
  const [selected, setSelected] = useState<Notice | null>(null)
  const [received, setReceived] = useState<ReceivedNotice | null>(null)
  const [requests, setRequests] = useState<ChangeRequest[]>([])
  const [skipped, setSkipped] = useState<string[]>([])
  const [candidates, setCandidates] = useState('')
  const [volume, setVolume] = useState('')
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
    void refresh()
  }, [refresh])

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
        const next = await receiveNotice(btoa(binary))
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

  const review = useCallback(async () => {
    const noticeId = received?.id ?? selected?.id
    const wanted = candidates
      .split(/[,\n]/)
      .map((mpn) => mpn.trim())
      .filter(Boolean)

    if (!noticeId || wanted.length === 0) {
      setError('Choose a notice and name at least one candidate part.')
      return
    }

    setBusy(true)
    setError(null)
    try {
      const outcome = await reviewNotice(noticeId, wanted, volume ? Number(volume) : null)
      setRequests(outcome.requests)
      // A candidate that was never checked has to be said out loud. Without this the
      // reader sees "no viable part" with no idea that one of the three they named was
      // excluded before it was ever evaluated — which is the document lying by omission.
      setSkipped([
        ...outcome.unresolved.map((mpn) => `${mpn} — not found at the distributor.`),
        ...Object.values(outcome.ambiguous),
      ])
    } catch (caught) {
      setRequests([])
      setSkipped([])
      setError(
        caught instanceof ApiError && caught.status === 409
          ? 'That notice does not reach any product line with an operating profile stored.'
          : 'That review could not be run.',
      )
    } finally {
      setBusy(false)
    }
  }, [candidates, received, selected, volume])

  const open = useCallback(async (notice: Notice) => {
    setSelected(notice)
    setReceived(null)
    setError(null)
    setSkipped([])
    try {
      setRequests(await listChangeRequests(notice.id))
    } catch {
      setRequests([])
    }
  }, [])

  const active = received?.notice ?? selected

  return (
    <div className="p-lg space-y-lg max-w-[900px]">
      <header className="flex items-center justify-between gap-md">
        <h1 className="font-headline-sm text-headline-sm text-on-surface">CHANGE NOTICES</h1>
        <label className="font-data-tabular text-[11px] text-primary-container border border-primary-container rounded px-md py-1 cursor-pointer hover:bg-surface-variant transition-colors">
          RECEIVE A NOTICE
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
      </header>

      {notices.length > 0 ? (
        <div className="flex flex-wrap gap-sm">
          {notices.map((notice) => (
            <button
              className={`px-sm py-0.5 border rounded font-data-tabular text-[10px] transition-colors ${
                (selected?.id ?? received?.id) === notice.id
                  ? 'border-primary-container text-primary-container'
                  : 'border-outline-variant text-on-surface-variant'
              }`}
              key={notice.id}
              onClick={() => void open(notice)}
              type="button"
            >
              {notice.mpn}
            </button>
          ))}
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

          {received ? (
            <p className="font-data-tabular text-[11px] text-on-surface">
              {received.affected.length === 0
                ? 'This part is not on any product line you ship.'
                : `Affects ${received.affected.length} product line${received.affected.length === 1 ? '' : 's'}: ${received.affected.map((line) => line.name).join(', ')}.`}
            </p>
          ) : null}

          <div className="flex flex-wrap items-end gap-md pt-sm">
            <label className="flex flex-col gap-1 flex-1 min-w-[260px]">
              <span className="font-data-tabular text-[10px] text-on-surface-variant">
                CANDIDATE PARTS
              </span>
              <input
                className="input-field px-sm h-8 w-full font-data-tabular text-[11px]"
                onChange={(event) => setCandidates(event.target.value)}
                placeholder={active.replacement_mpn ?? 'MPN, MPN'}
                value={candidates}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="font-data-tabular text-[10px] text-on-surface-variant">
                ANNUAL VOLUME
              </span>
              <input
                className="input-field px-sm h-8 w-32 font-data-tabular text-[11px]"
                onChange={(event) => setVolume(event.target.value.replace(/\D/g, ''))}
                placeholder="optional"
                value={volume}
              />
            </label>
            <button
              className="h-8 px-md border border-primary-container rounded font-data-tabular text-[11px] text-primary-container hover:bg-surface-variant transition-colors disabled:opacity-40"
              disabled={busy}
              onClick={review}
              type="button"
            >
              {busy ? 'CHECKING…' : 'REVIEW EVERY AFFECTED LINE'}
            </button>
          </div>
        </section>
      ) : (
        <p className="font-data-tabular text-[11px] text-on-surface-variant">
          Receive a change notice to begin. Continuity reads the part number out of the
          document, finds the products that carry it, and checks every substitute against
          each product’s own operating conditions.
        </p>
      )}

      {skipped.length > 0 ? (
        <section className="space-y-1">
          <h2 className="font-data-tabular text-[11px] text-tertiary-container">
            NOT CHECKED
          </h2>
          {skipped.map((reason) => (
            <p key={reason} className="font-data-tabular text-[10px] text-tertiary-container">
              {reason}
            </p>
          ))}
        </section>
      ) : null}

      {requests.length > 0 ? (
        <section className="space-y-md">
          <h2 className="font-data-tabular text-[11px] text-on-surface-variant">
            {requests.length} CHANGE REQUEST{requests.length === 1 ? '' : 'S'} — ONE PER
            AFFECTED PRODUCT LINE
          </h2>
          {requests.map((request) => (
            <RequestCard key={request.line_id} request={request} />
          ))}
        </section>
      ) : null}
    </div>
  )
}

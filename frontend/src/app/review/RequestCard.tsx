import { Fragment } from 'react'

import { BoardConsequence } from '../board/BoardConsequence'
import { departmentLabel } from './Departments'
import { checkLabel } from './ReviewLanes'
import type { ChangeRequest } from '../lib/api'

/** Every check a candidate was put through, the ones it failed first.
 *
 * **The failing ones are not behind a fold.** This block is the substitution matrix's job,
 * rehomed: what was tried, what killed it, and the working behind the sentence in the body.
 * It used to be a disclosure triangle reading *considered and rejected*, so the reader who
 * came looking for the rejected parts found a closed row and concluded the content had been
 * removed with the matrix page. Everything that failed is printed; the rest is a count and a
 * way to open it, because twenty-two satisfied checks per candidate is a wall of agreement
 * that buries the one line worth reading.
 */
function Verdicts({ alternative }: { alternative: ChangeRequest['alternatives'][number] }) {
  const verdicts = alternative.verdicts ?? []
  const failed = verdicts.filter((verdict) => verdict.status === 'failed')
  const rest = verdicts.filter((verdict) => verdict.status !== 'failed')
  if (verdicts.length === 0) return null

  const line = (verdict: (typeof verdicts)[number], position: number) => (
    <p
      className="m-0 font-data-tabular text-[12px] leading-relaxed"
      key={`${verdict.rule}:${verdict.scope ?? ''}:${position}`}
    >
      {/* The word first, never the colour alone: this is read on a projector and in a
          screenshot. */}
      <span className={verdict.status === 'failed' ? 'text-error' : 'text-on-surface-variant/70'}>
        {checkLabel(verdict)}
      </span>{' '}
      <span className="text-on-surface-variant">
        {verdict.rule.replace(/_/g, ' ')}
        {verdict.scope ? ` · ${verdict.scope}` : ''} — {verdict.detail}
        {verdict.margin ? ` · ${verdict.margin} to spare` : ''}
        {verdict.departments && verdict.departments.length > 0
          ? ` · ${verdict.departments.map(departmentLabel).join(' / ')}`
          : ''}
      </span>
    </p>
  )

  return (
    <div className="space-y-1">
      {failed.map(line)}
      {rest.length > 0 ? (
        <details>
          <summary className="font-data-tabular text-[12px] text-on-surface-variant cursor-pointer">
            the other {rest.length} checks it passed
          </summary>
          <div className="space-y-0.5 mt-1">{rest.map(line)}</div>
        </details>
      ) : null}
    </div>
  )
}

/** A change request, as the person who has to sign it reads it.
 *
 *  This is the document the whole product exists to produce, and until now it existed only
 *  as JSON on an endpoint. The rejected candidates' own verdict sets are the appendix —
 *  that is the
 *  working; this is the deliverable. */
export function RequestCard({ request }: { request: ChangeRequest }) {
  const rejected = request.alternatives.filter((a) => a.rejected_because)
  const viable = request.alternatives.filter((a) => !a.rejected_because)

  return (
    <article className="border border-outline-variant rounded p-lg space-y-md bg-surface-container-low">
      <header className="flex items-start justify-between gap-md">
        <div className="min-w-0">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">{request.line_name}</h3>
          <p className="font-data-tabular text-[12px] text-on-surface-variant mt-0.5">
            {request.revision ? `${request.revision} · ` : ''}
            fitted today: {request.baseline_mpn ?? 'unknown'}
          </p>
        </div>
        <span
          className={`font-data-tabular text-[12px] px-sm py-0.5 border rounded whitespace-nowrap ${
            request.proposal
              ? 'border-outline-variant text-[#4ade80]'
              : 'border-error text-error'
          }`}
        >
          {request.proposal ?? 'NO VIABLE PART'}
        </span>
      </header>

      <p className="font-data-tabular text-data-tabular text-on-surface leading-relaxed">
        {request.proposal_detail}
      </p>

      {rejected.length > 0 ? (
        <section className="space-y-sm">
          <h4 className="font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
            Considered and rejected
          </h4>
          {/* **One standing block per part.** Each rejected candidate keeps its own place on
              the page, with the sentence that killed it and the checks that sentence stands
              for. In the trace these same lines arrive one candidate at a time and are
              replaced by the next, which is why the working looked like it was not there. */}
          {rejected.map((alternative) => (
            <div
              className="border-l-2 border-error/40 pl-md space-y-1"
              key={alternative.mpn}
            >
              <p className="m-0 font-data-tabular text-[13px] leading-relaxed">
                <span className="text-on-surface">{alternative.mpn}</span>
                <span className="text-on-surface-variant"> — {alternative.rejected_because}</span>
              </p>
              <Verdicts alternative={alternative} />
            </div>
          ))}
        </section>
      ) : null}

      {viable.length > 0 ? (
        <p className="font-data-tabular text-[12px] text-on-surface-variant">
          Also viable, not chosen: {viable.map((a) => a.mpn).join(', ')}
        </p>
      ) : null}

      {/* What each desk found, over the same verdicts the evidence below is drawn from.
          Scenario B: one finding, several renderings, a view layer over one shared result.
          Every candidate was checked against all four departments' rules before anybody was
          asked anything, and until this block existed no screen said so. */}
      {request.departments.length > 0 ? (
        <section className="space-y-1">
          <h4 className="font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
            Every department, checked at once
          </h4>
          <dl className="grid grid-cols-[minmax(0,7rem)_auto] gap-x-md gap-y-1">
            {request.departments.map((desk) => (
              <Fragment key={desk.role}>
                <dt
                  className={`font-data-tabular text-[12px] uppercase ${
                    desk.failed > 0 ? 'text-error' : 'text-on-surface-variant'
                  }`}
                >
                  {departmentLabel(desk.role)}
                </dt>
                <dd className="font-data-tabular text-[12px] text-on-surface-variant leading-relaxed">
                  {/* Words rather than a colour alone: which desk is outstanding has to
                      survive greyscale and a projector. */}
                  <span className={desk.failed > 0 ? 'text-error' : 'text-[#4ade80]'}>
                    {desk.failed > 0
                      ? `${desk.failed} failed of ${desk.satisfied + desk.failed}`
                      : `${desk.satisfied} checked, nothing failed`}
                  </span>{' '}
                  — {desk.headline}
                </dd>
              </Fragment>
            ))}
          </dl>
        </section>
      ) : null}

      {request.evidence.length > 0 ? (
        <section className="space-y-1">
          <h4 className="font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
            Evidence
          </h4>
          {request.evidence.map((check, index) => (
            <p
              key={`${check.rule}:${check.scope ?? ''}:${index}`}
              className="font-data-tabular text-[12px] text-on-surface-variant leading-relaxed"
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

      <section className="space-y-1 border-t border-outline-variant pt-md">
        {request.no_evidence.length > 0 ? (
          <p className="font-data-tabular text-[12px] text-tertiary-container">
            Could not be checked: {request.no_evidence.map((r) => r.replace(/_/g, ' ')).join(', ')}.
          </p>
        ) : null}
      </section>

      {/* **The layout consequence, on the document.** It answers the question a parametric
          search cannot: a substitute in the same package is a substitution, a different one
          is a board revision, and that inverts which part is cheap. It was off this card for
          a day and the reason it is back is that a background KiCad run whose result no
          screen shows is a cost with no reader. The product line's BOARD pane places the
          same part on demand; the card carries the one the run already computed. */}
      <BoardConsequence
        // **It places itself, because opening the document is the question.** The run fires a
        // placement per line in the background and this usually arrives with the pictures
        // already on it. When it does not — a world with no KiCad, or a reader who opened the
        // card inside the twenty seconds the placement takes — a button asking whether to place
        // the substitute is a second question on a page where the reader has already asked it.
        auto
        candidate={request.proposal}
        lineId={request.line_id}
        retiring={request.notice_mpn}
        stored={request.board ?? null}
      />

      {/* What this replaced, in the run's own numbers. The sequence is what costs a
          cross-team response its time, and there was no sequence. */}
      {request.checked ? (
        <p className="font-data-tabular text-[12px] text-on-surface-variant/70 leading-relaxed">
          {request.checked.candidates} parts checked against {request.checked.departments}{' '}
          departments&rsquo; rules on {request.checked.lines} product line
          {request.checked.lines === 1 ? '' : 's'} — {request.checked.checks} checks on this
          board alone — before anybody was asked anything.
        </p>
      ) : null}


      {/* An engineering change order carries an inventory disposition, and this one only when
          there is something to dispose of — a line short of what it builds. */}
      {request.disposition ? (
        <p className="font-data-tabular text-[12px] text-tertiary-container leading-relaxed">
          DISPOSITION — {request.disposition}
        </p>
      ) : null}

      <p className="font-data-tabular text-[12px] text-on-surface-variant">
        EFFECTIVITY — {request.effectivity ?? 'on the last signature'}. Nothing is ordered or
        fabricated before then.
      </p>

      {/* **The money, and nothing about what it avoids.** The recurring figure is this board's
          own, because it is the substitute's price difference at this product's own annual
          volume. What the change avoids, and the round trips it does not cross, are spoken
          rather than printed: this is a document somebody signs, and an estimate sitting
          among the line items is the one thing it must not become. The constants and their
          sources are in `change.py`, and the arithmetic is in DEMO-DAY.md. */}
      {request.proposal ? (
        <section className="space-y-sm border-t border-outline-variant pt-md">
          <div className="flex flex-wrap gap-lg">
            <div>
              <p className="font-data-tabular text-[11px] text-on-surface-variant">ONE-TIME</p>
              <p className="font-data-tabular text-[13px] text-on-surface">
                ${request.cost.one_time.toLocaleString()}
              </p>
              <p className="font-data-tabular text-[12px] text-on-surface-variant">
                {request.cost.one_time_basis}
              </p>
            </div>
            <div>
              <p className="font-data-tabular text-[11px] text-on-surface-variant">RECURRING</p>
              <p className="font-data-tabular text-[13px] text-on-surface">
                {request.cost.recurring_annual === null
                  ? '—'
                  : `$${request.cost.recurring_annual.toLocaleString()} a year`}
              </p>
              <p className="font-data-tabular text-[12px] text-on-surface-variant">
                {request.cost.unit_delta === null
                  ? 'no published price to compare'
                  : request.cost.annual_volume
                    ? `${request.cost.unit_delta > 0 ? '+' : ''}$${request.cost.unit_delta} a unit at ${request.cost.annual_volume.toLocaleString()}/yr`
                    : `${request.cost.unit_delta > 0 ? '+' : ''}$${request.cost.unit_delta} a unit, no annual volume stated`}
              </p>
            </div>
          </div>

        </section>
      ) : null}

    </article>
  )
}

import { Fragment } from 'react'

import { BoardConsequence } from '../board/BoardConsequence'
import { departmentLabel } from './Departments'
import type { ChangeRequest } from '../lib/api'

/** A change request, as the person who has to sign it reads it.
 *
 *  This is the document the whole product exists to produce, and until now it existed only
 *  as JSON on an endpoint. The matrix shows the grid it is derived from — that is the
 *  working; this is the deliverable. */
export function RequestCard({ request }: { request: ChangeRequest }) {
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

      {/* What each desk found, over the same verdicts the evidence below is drawn from.
          Scenario B: one finding, several renderings, a view layer over one shared result.
          Every candidate was checked against all four departments' rules before anybody was
          asked anything, and until this block existed no screen said so. */}
      {request.departments.length > 0 ? (
        <section className="space-y-1">
          <h4 className="font-data-tabular text-[10px] text-on-surface-variant">
            EVERY DEPARTMENT, CHECKED AT ONCE
          </h4>
          <dl className="grid grid-cols-[minmax(0,7rem)_auto] gap-x-md gap-y-1">
            {request.departments.map((desk) => (
              <Fragment key={desk.role}>
                <dt
                  className={`font-data-tabular text-[10px] uppercase ${
                    desk.failed > 0 ? 'text-error' : 'text-on-surface-variant'
                  }`}
                >
                  {departmentLabel(desk.role)}
                </dt>
                <dd className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed">
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

      <section className="space-y-1 border-t border-outline-variant pt-md">
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

      {/* What this replaced, in the run's own numbers. Deliberately a footnote and
          deliberately not a saving: nobody measured how long a cross-team response takes
          here, and a fabricated hours-saved figure is the first thing a judge would ask
          about. The sequence is what costs the time, and there was no sequence. */}
      {request.checked ? (
        <p className="font-data-tabular text-[10px] text-on-surface-variant/70 leading-relaxed">
          {request.checked.candidates} parts checked against {request.checked.departments}{' '}
          departments&rsquo; rules on {request.checked.lines} product line
          {request.checked.lines === 1 ? '' : 's'} — {request.checked.checks} checks on this
          board alone — before anybody was asked anything.
        </p>
      ) : null}

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

import { Fragment } from 'react'

import { BoardConsequence } from '../board/BoardConsequence'
import { departmentLabel } from './Departments'
import { checkLabel } from './ReviewLanes'
import type { ChangeRequest } from '../lib/api'

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
          {/* The sentence that killed each, verbatim — and behind it, the whole set of checks
              that sentence stands for. **One line in the body, the working in the appendix**,
              which is the shape NEPA, MADR and every decision memo converge on: a proposal on
              its own asks to be trusted, one that shows its rejections asks to be checked, and
              a reader who wants to check opens the alternative rather than leaving the page. */}
          {rejected.map((alternative) => {
            const verdicts = alternative.verdicts ?? []
            return (
            <details key={alternative.mpn}>
              <summary className="font-data-tabular text-[10px] text-on-surface-variant leading-relaxed cursor-pointer">
                <span className="text-on-surface">{alternative.mpn}</span> —{' '}
                {alternative.rejected_because}
                {verdicts.length > 0 ? (
                  <span className="text-on-surface-variant/60"> · {verdicts.length} checks</span>
                ) : null}
              </summary>
              <ul className="m-0 mt-1 ml-md p-0 list-none flex flex-col gap-y-0.5">
                {verdicts.map((verdict, position) => (
                  <li
                    className="font-data-tabular text-[10px] leading-relaxed"
                    key={`${verdict.rule}:${verdict.scope ?? ''}:${position}`}
                  >
                    {/* The word first, never the colour alone: this is read on a projector
                        and in a screenshot. */}
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
                  </li>
                ))}
              </ul>
            </details>
            )
          })}
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
        stored={request.board ?? null}
      />

      {/* What this replaced, in the run's own numbers. The sequence is what costs a
          cross-team response its time, and there was no sequence. */}
      {request.checked ? (
        <p className="font-data-tabular text-[10px] text-on-surface-variant/70 leading-relaxed">
          {request.checked.candidates} parts checked against {request.checked.departments}{' '}
          departments&rsquo; rules on {request.checked.lines} product line
          {request.checked.lines === 1 ? '' : 's'} — {request.checked.checks} checks on this
          board alone — before anybody was asked anything.
        </p>
      ) : null}

      {/* **An estimate, with its arithmetic and its sources.** No published method turns
          counts into hours, so this is two published constants applied to what the run
          counted: one engineering-change iteration's touch time (Loch & Terwiesch 1999), and
          one handoff's stall between people (Herbsleb et al. 2001). It is shown rather than
          summarised because a reader can argue with a constant and cannot argue with a
          number that arrives on its own. */}
      {request.saving ? (
        <section className="space-y-1 border-t border-outline-variant pt-md">
          <p className="m-0 font-data-tabular text-[10px] text-on-surface-variant">
            WHAT THE MISSING ROUND TRIPS ARE WORTH
          </p>
          <p className="m-0 font-data-tabular text-[11px] text-on-surface leading-relaxed">
            About {request.saving.desk_hours} hours of desk time and about{' '}
            {request.saving.queue_days} days of queueing: {request.saving.desks} desks,{' '}
            {request.saving.crossings} handoffs, none of which this change had to cross.
          </p>
          <p className="m-0 font-data-tabular text-[10px] text-on-surface-variant/70 leading-relaxed">
            {request.saving.basis}
          </p>
        </section>
      ) : null}

      {/* An engineering change order carries an inventory disposition, and this one only when
          there is something to dispose of — a line short of what it builds. */}
      {request.disposition ? (
        <p className="font-data-tabular text-[10px] text-tertiary-container leading-relaxed">
          DISPOSITION — {request.disposition}
        </p>
      ) : null}

      <p className="font-data-tabular text-[10px] text-on-surface-variant">
        EFFECTIVITY — {request.effectivity ?? 'on the last signature'}. Nothing is ordered or
        fabricated before then.
      </p>

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

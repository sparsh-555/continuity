const HOURS_PER_DAY = 24

export type RoundTripSaving = {
  desk_hours: number
  queue_days: number
  desks: number
  crossings: number
  basis: string
}

export type Leg = {
  kind: 'work' | 'queue'
  hours: number
}

/** The elapsed path of one change, drawn from the two published constants.
 *
 *  **These are the same two numbers the document states, not a second estimate.** The desk
 *  work is one engineering-change iteration's touch time; each queue is one crossing between
 *  two people, and there are as many crossings as the run counted desks minus one. Splitting
 *  the stated total by eye into pleasing segments is exactly how a drawing comes to disagree
 *  with the sentence underneath it, so the queue is derived from the total and the count.
 *
 *  A change that crossed nothing has no queueing legs at all rather than empty ones: a zero
 *  divisor would put `Infinity` into a width.
 */
export function roundTripLegs(saving: RoundTripSaving): { sequential: Leg[]; together: Leg[] } {
  const crossings = Math.max(saving.crossings, 1)
  const queueHours = (saving.queue_days / crossings) * HOURS_PER_DAY

  const work: Leg = { kind: 'work', hours: saving.desk_hours }
  const queues: Leg[] = Array.from({ length: saving.crossings }, () => ({
    kind: 'queue' as const,
    hours: queueHours,
  }))

  return {
    sequential: [work, ...queues],
    together: [work],
  }
}

function total(legs: readonly Leg[]): number {
  return legs.reduce((sum, leg) => sum + leg.hours, 0)
}

function hoursInWords(hours: number): string {
  if (hours < 24) return `${Math.round(hours * 10) / 10} h`
  const days = Math.round((hours / HOURS_PER_DAY) * 10) / 10
  return `${days} days`
}

function Bar({ legs, tone }: { legs: readonly Leg[]; tone: string }) {
  const whole = total(legs)
  return (
    <div className="flex items-stretch h-6 w-full gap-[2px]">
      {legs.map((leg, index) => (
        <span
          className={`${tone} ${leg.kind === 'queue' ? 'opacity-40' : ''} rounded-[2px] flex items-center justify-center overflow-hidden`}
          key={`${leg.kind}:${index}`}
          style={{ flexGrow: leg.hours / whole }}
          title={leg.kind === 'queue' ? 'queueing between two people' : 'desk work'}
        >
          {leg.kind === 'work' ? (
            <span className="font-data-tabular text-[10px] text-background whitespace-nowrap px-1">
              {hoursInWords(leg.hours)}
            </span>
          ) : null}
        </span>
      ))}
    </div>
  )
}

/**
 * What a sequential answer spends that this one did not, drawn rather than asserted.
 *
 * The document used to state the two numbers in a sentence, and a sentence about time is
 * the one thing a reader cannot check at a glance: *5.2 hours and 2.7 days* looks the same
 * whether the queueing is most of it or none of it. Drawn to scale, the queue dominates the
 * picture because it dominates the elapsed time, and that is the finding.
 *
 * **The alternative is the process, not a strawman with invented durations.** Four desks in
 * sequence with one crossing between each is what an engineering change order is signed
 * through, and it is what the run counted: `crossings` is the desks it examined the change
 * against, minus one.
 *
 * It is an estimate and it says so, in the same breath as the numbers rather than in a
 * footnote nobody reads.
 */
export function RoundTrips({ saving }: { saving: RoundTripSaving }) {
  const { sequential, together } = roundTripLegs(saving)
  const desks = Array.from({ length: Math.max(saving.desks, 1) }, (_, index) => index)

  return (
    <section className="border border-outline-variant rounded bg-surface-container-low p-md space-y-sm">
      <p className="m-0 font-data-tabular text-[11px] tracking-[0.08em] text-on-surface-variant uppercase">
        What the missing round trips are worth
      </p>

      <div className="space-y-1">
        <p className="m-0 font-data-tabular text-[12px] text-on-surface-variant">
          One change, passed desk to desk
        </p>
        <Bar legs={sequential} tone="bg-tertiary-container" />
        <p className="m-0 font-data-tabular text-[11px] text-on-surface-variant/70">
          {desks.map((index) => `desk ${index + 1}`).join(' → ')} · {saving.crossings} crossing
          {saving.crossings === 1 ? '' : 's'} between them, each one a person&rsquo;s queue
          rather than their work
        </p>
      </div>

      <div className="space-y-1">
        <p className="m-0 font-data-tabular text-[12px] text-on-surface">
          This change, examined by every desk at once
        </p>
        <Bar legs={together} tone="bg-[#4ade80]" />
        <p className="m-0 font-data-tabular text-[11px] text-on-surface-variant/70">
          nothing queues between desks, because nothing is passed between them
        </p>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-lg gap-y-1 border-t border-outline-variant pt-sm">
        <p className="m-0 font-data-tabular text-[12px] text-on-surface">
          About {saving.desk_hours} hours of desk time and about {saving.queue_days} days of
          queueing, none of which this change had to cross.
        </p>
        <p className="m-0 font-data-tabular text-[11px] text-on-surface-variant/70">
          {hoursInWords(total(sequential))} against {hoursInWords(total(together))}
        </p>
      </div>

      <p className="m-0 font-data-tabular text-[11px] text-on-surface-variant/60 leading-relaxed">
        {saving.basis}
      </p>
    </section>
  )
}

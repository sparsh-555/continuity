/** How a memory-graph node and edge should look, kept apart from the canvas that draws it.
 *
 * Pulled out of `memory.tsx` because these are the decisions worth arguing about and worth
 * testing, and because a `CanvasRenderingContext2D` is a poor place to read them from.
 *
 * ## Why the encoding is what it is
 *
 * A retired part used to be the same saturated orange as everything else with a 2 px ring
 * around it, and at the zoom the graph settles at, a pale ring on a saturated fill is close
 * to invisible. Four things changed, in the order that a lineage-visualisation writeup, WCAG
 * 1.4.1 and G6's own state documentation agree on:
 *
 * - **The fill carries it, not the ring.** A retired part differs in lightness as well as
 *   hue, so it separates in greyscale and for a reader who does not see the orange-red
 *   pairing at all.
 * - **A word backs the colour up.** `NRND` or `OBSOLETE` under the part number, because
 *   colour must never be the only carrier and a screenshot travels without the legend.
 * - **The edges say which kind of gone.** Dashed grey already meant *was on this board and
 *   was replaced*; a part that is retired and **still fitted** drew a line identical to a
 *   healthy one, so the three edges carrying the whole story were the three least
 *   distinguishable things on screen. Those are now dashed, warm and heavier.
 * - **Nothing else was added.** The graph already spends shape on kind and area on uses.
 *   Encoding one more variable without removing one is how these pictures become unreadable.
 */

export type Lifecycle = 'active' | 'nrnd' | 'obsolete' | 'unknown' | null

export const HEALTHY_FILL = '#f2a25c'
export const RETIRED_FILL = '#9c6f63'
/** Desaturated and darker than the healthy orange, so the two differ in lightness. */
export const RETIRED_STROKE = '#ffb4ab'
export const DECIDED_STROKE = '#f5d84a'
export const EDGE_COLOUR = '#849396'
export const RETIRING_EDGE_COLOUR = '#ffb4ab'

export function isRetired(lifecycle: Lifecycle): boolean {
  return lifecycle === 'nrnd' || lifecycle === 'obsolete'
}

export function partAppearance(lifecycle: Lifecycle, decided: number) {
  const retired = isRetired(lifecycle)
  return {
    retired,
    fill: retired ? RETIRED_FILL : HEALTHY_FILL,
    // Heavier on a retired part, because line width is the one channel that survives
    // greyscale, colour blindness and a projector all at once.
    stroke: retired ? RETIRED_STROKE : decided ? DECIDED_STROKE : null,
    strokeWidth: retired ? 3 : 2,
    // The badge counts decisions somebody took. A retired part wears its lifecycle word
    // instead, so one node never carries two marks that mean different things.
    badge: !retired && decided > 0 ? decided : null,
    note: retired ? (lifecycle ?? '').toUpperCase() : null,
  }
}

export function edgeAppearance({
  historical,
  retiredEndpoint,
}: {
  historical: boolean
  retiredEndpoint: boolean
}) {
  if (historical) {
    // Was on this board, then replaced. Grey, because it is finished.
    return { colour: EDGE_COLOUR, dashed: true, width: 1, alpha: 0.45 }
  }
  if (retiredEndpoint) {
    // Is on this board and going away, which is the whole subject of the notice.
    return { colour: RETIRING_EDGE_COLOUR, dashed: true, width: 2, alpha: 0.75 }
  }
  return { colour: EDGE_COLOUR, dashed: false, width: 1, alpha: 0.45 }
}

export const LEGEND: ReadonlyArray<{ label: string; fill: string; note: string }> = [
  { label: 'Part', fill: HEALTHY_FILL, note: 'in production' },
  { label: 'Retired', fill: RETIRED_FILL, note: 'NRND or obsolete' },
  { label: 'Going away', fill: RETIRING_EDGE_COLOUR, note: 'fitted, and retired' },
  { label: 'Replaced', fill: EDGE_COLOUR, note: 'was on this board' },
]

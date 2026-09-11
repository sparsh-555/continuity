import type { BoardConsequence as Consequence } from '../lib/api'

/** Board placements already computed in this session, keyed by what decides one.
 *
 * A KiCad run is several seconds — measured at 3365 ms cold — and the answer for a given
 * product line, retired part and candidate does not change while the page is open. Without
 * this the placement ran again every time the component mounted or the product line
 * refetched, which is not merely slow: the picture is replaced by **PLACING…** while it
 * happens, so a poll landing behind the board view takes the board away from whoever is
 * looking at it. That failed a browser test once, which is how it was found.
 *
 * Session-lifetime and in memory on purpose. The server caches the render itself by the
 * bundle's digest, so this is about not asking twice, not about storage.
 */
const LIMIT = 24

const placed = new Map<string, Consequence>()

export function placementKey(lineId: string, retiring: string, candidate: string): string {
  return `${lineId} ${retiring.toUpperCase()} ${candidate.toUpperCase()}`
}

export function recallPlacement(
  lineId: string,
  retiring: string,
  candidate: string | null,
): Consequence | null {
  if (!candidate) return null
  return placed.get(placementKey(lineId, retiring, candidate)) ?? null
}

export function rememberPlacement(
  lineId: string,
  retiring: string,
  candidate: string,
  outcome: Consequence,
): void {
  const key = placementKey(lineId, retiring, candidate)
  placed.delete(key)
  placed.set(key, outcome)
  while (placed.size > LIMIT) {
    const oldest = placed.keys().next()
    if (oldest.done) break
    placed.delete(oldest.value)
  }
}

/** Test seam. Nothing in the app calls this. */
export function forgetPlacements(): void {
  placed.clear()
}

/** Whether this instance has told us it has no KiCad.
 *
 * **A deployment without KiCad should not ask once per document.** The deployed service runs
 * on a host with no container, so `runner.available()` is false and the streaming endpoint
 * answers 503. The card places itself now rather than offering a button, which means an
 * unsolicited "this instance has no KiCad configured" would appear on every change request a
 * visitor opens, reading as a broken feature rather than an absent one.
 *
 * Learned once, from the server's own answer, and remembered for the session. Nothing is
 * assumed: on a machine with KiCad the flag never rises, and the flag is only ever set by a
 * 503 that came back from the server.
 */
let noKicad = false

export function kicadMissing(): boolean {
  return noKicad
}

export function noteKicadMissing(): void {
  noKicad = true
}

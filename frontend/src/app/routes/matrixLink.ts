/** The link that turns `/matrix` from a form into a destination.
 *
 * The matrix is the only screen showing every candidate against every board including the
 * ones that lost, and it was asking the reader to supply what the review had just worked
 * out: tick the product lines, type the reference designator, type the part numbers. All
 * three are already on the page the reader is standing on.
 *
 * **One reference designator, and only the lines that carry it.** `POST /matrix` takes a
 * single slot for the whole grid and refuses a line that does not have that designator, so
 * a link naming U1 must not carry a board whose regulator is U7 — it would open on an
 * error. Sending the boards that agree is a smaller answer than the reader might have
 * wanted and it is a correct one, and the count is on the link so nobody is surprised.
 */

export type Exposure = { line_id: string; refdes: string[] }

export function matrixQuery({
  affected,
  candidates,
}: {
  affected: Exposure[]
  candidates: string[]
}): { search: string; lines: number; slot: string } | null {
  const wanted = candidates.map((mpn) => mpn.trim()).filter(Boolean)
  const unique = [...new Set(wanted)]
  if (unique.length === 0) return null

  // The designator most of these boards use. Boards do disagree about refdes far more often
  // than they agree, and the grid can only ask about one at a time.
  const counts = new Map<string, number>()
  for (const line of affected) {
    for (const refdes of new Set(line.refdes)) {
      counts.set(refdes, (counts.get(refdes) ?? 0) + 1)
    }
  }
  const [slot] = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0] ?? []
  if (!slot) return null

  const lines = affected.filter((line) => line.refdes.includes(slot)).map((line) => line.line_id)
  if (lines.length === 0) return null

  const search = new URLSearchParams({
    lines: lines.join(','),
    slot,
    candidates: unique.join(','),
  }).toString()
  return { search, lines: lines.length, slot }
}

/** What a prefilled `/matrix` was asked to show, or nulls when it was opened bare. */
export function matrixPrefill(search: string) {
  const params = new URLSearchParams(search)
  const split = (value: string | null) =>
    (value ?? '').split(',').map((part) => part.trim()).filter(Boolean)
  const lines = split(params.get('lines'))
  const candidates = split(params.get('candidates'))
  const slot = (params.get('slot') ?? '').trim()
  // All three or none. A half-filled form that runs itself would show a grid nobody asked
  // for, and one that does not run leaves the reader wondering what the link did.
  if (!lines.length || !candidates.length || !slot) return null
  return { lines, slot, candidates }
}

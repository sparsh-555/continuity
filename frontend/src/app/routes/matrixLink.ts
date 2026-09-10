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

/** One candidate, named with whoever makes it where the caller knows.
 *
 * **A part number alone does not name a part.** The catalogue leg returns `LD1117-3.3` from
 * five manufacturers and `TLV1117LV33DCYR` from two, with different stock and different
 * supply ceilings, and the review weighed exactly one of them. Passing only the number makes
 * the matrix re-source it by exact-number search, which for a part this company has never
 * bought comes back empty — so the grid lost three columns and said *not found at the
 * distributor* about parts the review had just checked.
 */
export type NamedCandidate = { mpn: string; manufacturer?: string | null }

/** `mpn|manufacturer`, or just `mpn` where there is nothing to say.
 *
 * The separator matters: manufacturer names contain commas (`UMW(Youtai Semiconductor Co.,
 * Ltd.)`), so a comma-separated pair would split in the middle of a company.
 */
export function encodeCandidate(candidate: NamedCandidate): string {
  return candidate.manufacturer ? `${candidate.mpn}|${candidate.manufacturer}` : candidate.mpn
}

/** What separates one candidate from the next in the query string.
 *
 * **Not a comma, and that is the whole reason it is named here.** Company names contain
 * commas — `UMW(Youtai Semiconductor Co., Ltd.)` is one of the demo's own candidates — so a
 * comma-separated list splits in the middle of a manufacturer and the part comes back with
 * a truncated maker, which then does not match any listing. A newline cannot appear in a
 * company name and survives the round trip through `URLSearchParams`.
 */
export const LIST_SEPARATOR = '\n'

export function decodeCandidate(token: string): NamedCandidate {
  const at = token.indexOf('|')
  return at === -1
    ? { mpn: token }
    : { mpn: token.slice(0, at), manufacturer: token.slice(at + 1) }
}

export function matrixQuery({
  affected,
  candidates,
}: {
  affected: Exposure[]
  candidates: NamedCandidate[]
}): {
  search: string
  lines: number
  slot: string
  /** What the names carry beyond the part number, for the request body. */
  manufacturers: Record<string, string>
} | null {
  const named = candidates
    .map((candidate) => ({
      ...candidate,
      mpn: candidate.mpn.trim(),
      manufacturer: candidate.manufacturer?.trim() || null,
    }))
    .filter((candidate) => candidate.mpn)
  // A part number can appear twice under one maker across three boards' documents; the
  // last name wins, and two different makers for one number would be a contradiction the
  // review could not have produced.
  const unique = [...new Map(named.map((c) => [c.mpn, c])).values()]
  if (unique.length === 0) return null
  const manufacturers: Record<string, string> = {}
  for (const candidate of unique) {
    if (candidate.manufacturer) manufacturers[candidate.mpn] = candidate.manufacturer
  }

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
    candidates: unique.map(encodeCandidate).join(LIST_SEPARATOR),
  }).toString()
  return { search, lines: lines.length, slot, manufacturers }
}

/** What a prefilled `/matrix` was asked to show, or nulls when it was opened bare. */
export function matrixPrefill(search: string) {
  const params = new URLSearchParams(search)
  const split = (value: string | null, on: string = ',') =>
    (value ?? '').split(on).map((part) => part.trim()).filter(Boolean)
  const lines = split(params.get('lines'))
  const candidates = split(params.get('candidates'), LIST_SEPARATOR).map(decodeCandidate)
  const slot = (params.get('slot') ?? '').trim()
  // All three or none. A half-filled form that runs itself would show a grid nobody asked
  // for, and one that does not run leaves the reader wondering what the link did.
  if (!lines.length || !candidates.length || !slot) return null
  const manufacturers: Record<string, string> = {}
  for (const candidate of candidates) {
    if (candidate.manufacturer) manufacturers[candidate.mpn] = candidate.manufacturer
  }
  return { lines, slot, candidates, manufacturers }
}

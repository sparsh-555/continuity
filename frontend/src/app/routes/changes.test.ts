import { describe, expect, test } from 'bun:test'

import { noticeIdentity, skippedFor } from './changes'

describe('changes notice reopening', () => {
  test('hydrates the stored not-checked candidates without starting another review', () => {
    expect(
      skippedFor({
        id: 'notice-1',
        mpn: 'AMS1117-3.3',
        mpn_line: 'Affected part: AMS1117-3.3',
        manufacturer: 'Advanced Monolithic Systems',
        effective_date: null,
        replacement_mpn: null,
        reason: null,
        source: 'mail',
        created_at: '2026-09-11T00:00:00Z',
        review_skipped: [{ mpn: 'LD1117', reason: 'the listing is ambiguous' }],
      }),
    ).toEqual([{ mpn: 'LD1117', reason: 'the listing is ambiguous' }])
  })

  const notice = (over: Partial<Notice> = {}): Notice =>
    ({
      id: 'notice-1',
      reference: 'PCN 2026-114',
      reference_line: 'PCN 2026-114 · Advanced Monolithic Systems',
      mpn: 'AMS1117-3.3',
      mpn_line: 'Affected part: AMS1117-3.3',
      manufacturer: 'Advanced Monolithic Systems',
      effective_date: null,
      replacement_mpn: null,
      reason: null,
      source: 'mail',
      created_at: '2026-09-11T00:00:00Z',
      review_skipped: [],
      ...over,
    }) as Notice

  test('keeps same-part notices distinguishable by the document reference', () => {
    const label = noticeIdentity(notice())

    expect(label).toContain('PCN 2026-114')
    expect(label).toContain('received ')
    expect(noticeIdentity(notice({ reference: 'PCN 2026-118' }))).not.toBe(label)
  })

  test('falls back to the received date when the notice carries no reference', () => {
    const label = noticeIdentity(notice({ reference: null, reference_line: null }))

    expect(label).toContain('received ')
    expect(label).not.toContain('PCN')
  })

  test("the received date is the reader's own day, not a UTC truncation", () => {
    // Two instants inside one local calendar day, found by asking the clock rather than by
    // assuming a timezone. A slice of the stored string splits them wherever the reader is
    // east or west of Greenwich; the local day does not.
    const noon = new Date('2026-09-12T12:00:00Z')
    const firstMoment = new Date(noon)
    firstMoment.setHours(0, 0, 0, 0)
    const lastMoment = new Date(noon)
    lastMoment.setHours(23, 59, 59, 999)

    expect(noticeIdentity(notice({ created_at: firstMoment.toISOString() }))).toBe(
      noticeIdentity(notice({ created_at: lastMoment.toISOString() })),
    )

    // And the day either side of it is a different day.
    const before = new Date(firstMoment.getTime() - 1)
    expect(noticeIdentity(notice({ created_at: before.toISOString() }))).not.toBe(
      noticeIdentity(notice({ created_at: firstMoment.toISOString() })),
    )
  })
})

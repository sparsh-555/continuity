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

  test('keeps same-part notices distinguishable by the document reference and received date', () => {
    expect(
      noticeIdentity({
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
      }),
    ).toBe('PCN 2026-114 · received 2026-09-11')
  })
})

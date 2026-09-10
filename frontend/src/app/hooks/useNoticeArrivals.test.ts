import { describe, expect, test } from 'bun:test'

import { newlyArrivedNotices } from './useNoticeArrivals'

describe('newlyArrivedNotices', () => {
  test('does not announce the initial baseline, then returns each stored notice once', () => {
    const initial = [
      { id: 'already-known', mpn: 'LM1117-3.3' },
    ]
    const afterMail = [
      { id: 'mailed', mpn: 'AMS1117-3.3' },
      ...initial,
    ]

    const known = new Set(initial.map((notice) => notice.id))

    expect(newlyArrivedNotices(known, afterMail)).toEqual([{ id: 'mailed', mpn: 'AMS1117-3.3' }])
    expect(newlyArrivedNotices(known, afterMail)).toEqual([])
  })
})

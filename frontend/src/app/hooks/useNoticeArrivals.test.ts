import { describe, expect, test } from 'bun:test'

import { newlyArrivedNotices } from './useNoticeArrivals'

describe('newlyArrivedNotices', () => {
  test('does not mark an arrival seen until its notification has been assembled', () => {
    const initial = [
      { id: 'already-known', mpn: 'LM1117-3.3' },
    ]
    const afterMail = [
      { id: 'mailed', mpn: 'AMS1117-3.3' },
      ...initial,
    ]

    const known = new Set(initial.map((notice) => notice.id))
    const inFlight = new Set<string>()

    const arrived = newlyArrivedNotices(known, inFlight, afterMail)
    expect(arrived).toEqual([{ id: 'mailed', mpn: 'AMS1117-3.3' }])
    expect(known).toEqual(new Set(['already-known']))

    arrived.forEach((notice) => inFlight.add(notice.id))
    expect(newlyArrivedNotices(known, inFlight, afterMail)).toEqual([])

    arrived.forEach((notice) => inFlight.delete(notice.id))
    expect(newlyArrivedNotices(known, inFlight, afterMail)).toEqual([{ id: 'mailed', mpn: 'AMS1117-3.3' }])

    arrived.forEach((notice) => known.add(notice.id))
    expect(newlyArrivedNotices(known, inFlight, afterMail)).toEqual([])
  })
})

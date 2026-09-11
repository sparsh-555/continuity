import { describe, expect, test } from 'bun:test'

import { signatureSummary, signingOrder } from './Signatures'

describe('who has signed', () => {
  test('every desk is listed in the order the rest of the product uses', () => {
    // The order is fixed so four desks never reorder between two surfaces, and it is the
    // same order `DEPARTMENT_ORDER` gives the server. A row that reordered itself as
    // signatures arrived would move the tick the reader was following.
    expect(signingOrder(['quality', 'engineering', 'production', 'procurement'])).toEqual([
      'engineering',
      'procurement',
      'production',
      'quality',
    ])
  })

  test('a desk nobody has heard of is still listed, after the four that are known', () => {
    // A rule can be owned by a desk this build has no label for. Dropping it would make the
    // row claim the change needs three signatures when it needs four.
    expect(signingOrder(['quality', 'logistics'])).toEqual(['quality', 'logistics'])
  })

  test('the count is of desks, in words, with the outstanding ones named', () => {
    expect(signatureSummary(['engineering', 'procurement', 'production', 'quality'], ['engineering'])).toBe(
      '1 of 4 signed. Waiting on PROCUREMENT, PRODUCTION and QUALITY.',
    )
  })

  test('a fully signed change says so without naming anybody as outstanding', () => {
    const roles = ['engineering', 'procurement']

    expect(signatureSummary(roles, roles)).toBe('2 of 2 signed.')
  })

  test('a change nobody has signed still names every desk it is waiting on', () => {
    // Nought of two is the less useful half. The reader who has just arrived is the one who
    // needs to know whether any of it is theirs.
    expect(signatureSummary(['engineering', 'quality'], [])).toBe(
      '0 of 2 signed. Waiting on DESIGN and QUALITY.',
    )
  })

  test('signatures from a desk that is not on the list do not inflate the count', () => {
    // The server records the desks that signed against the desks that must. If a role was
    // removed from the routing table between the decision and the reading, the row has to
    // report what the decision now requires rather than what it once did.
    expect(signatureSummary(['engineering', 'quality'], ['engineering', 'logistics'])).toBe(
      '1 of 2 signed. Waiting on QUALITY.',
    )
  })
})

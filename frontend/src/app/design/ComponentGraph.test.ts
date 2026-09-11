import { expect, test } from 'bun:test'

import { legendRows } from './ComponentGraph'
import type { GraphSlot } from '../lib/types'

test('a state the legend has no row for is left out rather than taking the page down', () => {
  // **The landing page replays a recording, and a recording carries the vocabulary of the
  // day it was made.** `not_assessed` is one of the states the engine has since deleted, so
  // it arrives here on the very first screen a visitor sees. A missing row used to be an
  // `undefined` that reached the render and replaced that screen with an error boundary,
  // which is a high price for a legend entry nobody could have drawn.
  const retired = 'not_assessed' as unknown as GraphSlot['status']
  const rows = legendRows(['pass', retired])

  // The length is the assertion, not `toEqual`: `toEqual` treats an `undefined` element as
  // no element at all, so the version of this test that checked the array's contents passed
  // while the second row was still being handed to the render.
  expect(rows.length).toBe(1)
  expect(rows).toEqual([{ label: 'Valid', fill: '#4ade80' }])
})

test('the graph legend describes only states present on a resting board', () => {
  expect(legendRows(['unchecked'])).toEqual([
    { label: 'Fitted · unchecked', fill: '#3F444E' },
  ])
})

test('the graph legend names each distinct state present while a review runs', () => {
  expect(legendRows(['pass', 'searching', 'conflict', 'pass', 'accepted'])).toEqual([
    { label: 'Valid', fill: '#4ade80' },
    { label: 'Checking', fill: '#00E5FF' },
    { label: 'Conflict', fill: '#ffb4ab' },
    { label: 'Accepted', fill: '#fbbf24' },
  ])
})

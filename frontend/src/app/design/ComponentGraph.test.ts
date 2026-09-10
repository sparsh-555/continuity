import { expect, test } from 'bun:test'

import { legendRows } from './ComponentGraph'

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

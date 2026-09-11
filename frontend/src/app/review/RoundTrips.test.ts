import { describe, expect, test } from 'bun:test'

import { roundTripLegs, type RoundTripSaving } from './RoundTrips'

const saving = (over: Partial<RoundTripSaving> = {}): RoundTripSaving => ({
  desk_hours: 5.2,
  queue_days: 2.7,
  desks: 4,
  crossings: 3,
  basis: '',
  ...over,
})

describe('the round trips a change did not have to cross', () => {
  test('one stretch of desk work and one queue for every crossing', () => {
    const { sequential, together } = roundTripLegs(saving())

    expect(sequential.map((leg) => leg.kind)).toEqual(['work', 'queue', 'queue', 'queue'])
    expect(together.map((leg) => leg.kind)).toEqual(['work'])
  })

  test('each queue is the same published stall, not the total split by eye', () => {
    // 0.9 days of 24 hours is one handoff. Three of them are the 2.7 days the document
    // states, and a leg that did not come to that would make the drawing disagree with the
    // sentence underneath it.
    const { sequential } = roundTripLegs(saving())
    const queues = sequential.filter((leg) => leg.kind === 'queue')

    expect(queues.map((leg) => leg.hours)).toEqual([21.6, 21.6, 21.6])
    expect(queues.reduce((total, leg) => total + leg.hours, 0)).toBeCloseTo(2.7 * 24, 6)
  })

  test('a change that crossed nothing is drawn as one stretch, with no empty queue', () => {
    // A division by zero crossings would put `Infinity` in a width, which React renders as
    // a bar the width of the page. A single-desk change has no queueing to draw.
    const { sequential, together } = roundTripLegs(saving({ desks: 1, crossings: 0, queue_days: 0 }))

    expect(sequential.map((leg) => leg.kind)).toEqual(['work'])
    expect(together).toEqual(sequential)
  })

  test('the drawing is to scale, so the queue is visibly the larger half', () => {
    const { sequential } = roundTripLegs(saving())
    const work = sequential.find((leg) => leg.kind === 'work')

    expect(work?.hours).toBe(5.2)
    // 64.8 hours of queueing against 5.2 of work. Anything that did not show the queue as
    // the dominant part would be hiding the finding in the drawing.
    const total = sequential.reduce((sum, leg) => sum + leg.hours, 0)
    expect(work!.hours / total).toBeLessThan(0.1)
  })
})

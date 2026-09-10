import { expect, test } from 'bun:test'

import { edgeAppearance, partAppearance, HEALTHY_FILL, RETIRED_FILL } from './memoryGraph'

test('a retired part differs from a healthy one in fill, not only in a ring', () => {
  const healthy = partAppearance('active', 0)
  const retired = partAppearance('nrnd', 0)

  expect(healthy.fill).toBe(HEALTHY_FILL)
  expect(retired.fill).toBe(RETIRED_FILL)
  expect(retired.fill).not.toBe(healthy.fill)
  expect(retired.strokeWidth).toBeGreaterThan(healthy.strokeWidth)
})

test('a retired part says so in words, so the colour is never the only carrier', () => {
  expect(partAppearance('nrnd', 0).note).toBe('NRND')
  expect(partAppearance('obsolete', 0).note).toBe('OBSOLETE')
  expect(partAppearance('active', 0).note).toBeNull()
  expect(partAppearance(null, 0).note).toBeNull()
})

test('one node never carries two marks that mean different things', () => {
  expect(partAppearance('active', 3).badge).toBe(3)
  expect(partAppearance('nrnd', 3).badge).toBeNull()
  expect(partAppearance('nrnd', 3).note).toBe('NRND')
})

test('the two kinds of gone are told apart', () => {
  const replaced = edgeAppearance({ historical: true, retiredEndpoint: true })
  const goingAway = edgeAppearance({ historical: false, retiredEndpoint: true })
  const healthy = edgeAppearance({ historical: false, retiredEndpoint: false })

  expect(replaced.dashed).toBe(true)
  expect(goingAway.dashed).toBe(true)
  expect(goingAway.colour).not.toBe(replaced.colour)
  expect(goingAway.width).toBeGreaterThan(replaced.width)

  expect(healthy.dashed).toBe(false)
  expect(healthy.width).toBe(1)
})

test('an edge to a part still fitted and going away is not drawn like a healthy one', () => {
  const goingAway = edgeAppearance({ historical: false, retiredEndpoint: true })
  const healthy = edgeAppearance({ historical: false, retiredEndpoint: false })

  expect(goingAway).not.toEqual(healthy)
})

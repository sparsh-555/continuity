import { beforeEach, expect, test } from 'bun:test'

import {
  forgetPlacements,
  placementKey,
  recallPlacement,
  rememberPlacement,
} from './placements'
import type { BoardConsequence } from '../lib/api'

const outcome = (candidate: string) => ({ candidate }) as unknown as BoardConsequence

beforeEach(() => forgetPlacements())

test('the same board, part and candidate is asked for once', () => {
  rememberPlacement('line-a', 'AMS1117-3.3', 'NCP1117ST33T3G', outcome('NCP1117ST33T3G'))

  expect(recallPlacement('line-a', 'AMS1117-3.3', 'NCP1117ST33T3G')).toEqual(
    outcome('NCP1117ST33T3G'),
  )
})

test('a different candidate, or a different board, is a different placement', () => {
  rememberPlacement('line-a', 'AMS1117-3.3', 'NCP1117ST33T3G', outcome('NCP1117ST33T3G'))

  expect(recallPlacement('line-a', 'AMS1117-3.3', 'TLV1117LV33DCYR')).toBeNull()
  expect(recallPlacement('line-b', 'AMS1117-3.3', 'NCP1117ST33T3G')).toBeNull()
})

test('a part number is a part number however it is cased', () => {
  rememberPlacement('line-a', 'AMS1117-3.3', 'NCP1117ST33T3G', outcome('NCP1117ST33T3G'))

  expect(recallPlacement('line-a', 'ams1117-3.3', 'ncp1117st33t3g')).not.toBeNull()
})

test('nothing to place is nothing to recall', () => {
  expect(recallPlacement('line-a', 'AMS1117-3.3', null)).toBeNull()
})

test('the key separates fields that could otherwise run together', () => {
  expect(placementKey('a', 'B', 'C')).not.toBe(placementKey('aB', '', 'C'))
})

test('it does not grow without bound', () => {
  for (let index = 0; index < 40; index += 1) {
    rememberPlacement('line-a', 'AMS1117-3.3', `PART-${index}`, outcome(`PART-${index}`))
  }

  expect(recallPlacement('line-a', 'AMS1117-3.3', 'PART-0')).toBeNull()
  expect(recallPlacement('line-a', 'AMS1117-3.3', 'PART-39')).not.toBeNull()
})

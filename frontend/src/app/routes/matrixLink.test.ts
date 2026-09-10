import { expect, test } from 'bun:test'

import { matrixPrefill, matrixQuery } from './matrixLink'

const affected = [
  { line_id: 'a', refdes: ['u1'] },
  { line_id: 'b', refdes: ['u1'] },
  { line_id: 'c', refdes: ['u1'] },
]

test('the link carries what the review already knows', () => {
  const link = matrixQuery({
    affected,
    candidates: ['AMS1117-3.3', 'NCP1117ST33T3G', 'TLV1117LV33DCYR'],
  })

  expect(link).not.toBeNull()
  expect(link!.slot).toBe('u1')
  expect(link!.lines).toBe(3)
  expect(matrixPrefill(link!.search)).toEqual({
    lines: ['a', 'b', 'c'],
    slot: 'u1',
    candidates: ['AMS1117-3.3', 'NCP1117ST33T3G', 'TLV1117LV33DCYR'],
  })
})

test('a board whose part sits elsewhere is left out rather than opening on an error', () => {
  const link = matrixQuery({
    affected: [...affected, { line_id: 'd', refdes: ['u7'] }],
    candidates: ['AMS1117-3.3'],
  })

  expect(link!.slot).toBe('u1')
  expect(link!.lines).toBe(3)
  expect(matrixPrefill(link!.search)!.lines).not.toContain('d')
})

test('one part number is never repeated, however many rejections name it', () => {
  const link = matrixQuery({
    affected,
    candidates: ['AMS1117-3.3', 'NCP1117ST33T3G', 'AMS1117-3.3', ' NCP1117ST33T3G '],
  })

  expect(matrixPrefill(link!.search)!.candidates).toEqual(['AMS1117-3.3', 'NCP1117ST33T3G'])
})

test('nothing to show is no link at all, rather than one that opens on an error', () => {
  expect(matrixQuery({ affected, candidates: [] })).toBeNull()
  expect(matrixQuery({ affected: [], candidates: ['AMS1117-3.3'] })).toBeNull()
  expect(matrixQuery({ affected: [{ line_id: 'a', refdes: [] }], candidates: ['X'] })).toBeNull()
})

test('a half-filled query runs nothing', () => {
  expect(matrixPrefill('lines=a&slot=u1')).toBeNull()
  expect(matrixPrefill('lines=a&candidates=X')).toBeNull()
  expect(matrixPrefill('slot=u1&candidates=X')).toBeNull()
  expect(matrixPrefill('')).toBeNull()
})

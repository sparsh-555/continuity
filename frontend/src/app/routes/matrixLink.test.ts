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
    candidates: [
      { mpn: 'AMS1117-3.3' },
      { mpn: 'NCP1117ST33T3G' },
      { mpn: 'TLV1117LV33DCYR' },
    ],
  })

  expect(link).not.toBeNull()
  expect(link!.slot).toBe('u1')
  expect(link!.lines).toBe(3)
  expect(matrixPrefill(link!.search)!.lines).toEqual(['a', 'b', 'c'])
  expect(matrixPrefill(link!.search)!.slot).toBe('u1')
  expect(matrixPrefill(link!.search)!.candidates.map((c) => c.mpn)).toEqual([
    'AMS1117-3.3', 'NCP1117ST33T3G', 'TLV1117LV33DCYR',
  ])
})

test('a board whose part sits elsewhere is left out rather than opening on an error', () => {
  const link = matrixQuery({
    affected: [...affected, { line_id: 'd', refdes: ['u7'] }],
    candidates: [{ mpn: 'AMS1117-3.3' }],
  })

  expect(link!.slot).toBe('u1')
  expect(link!.lines).toBe(3)
  expect(matrixPrefill(link!.search)!.lines).not.toContain('d')
})

test('one part number is never repeated, however many rejections name it', () => {
  const link = matrixQuery({
    affected,
    candidates: [
      { mpn: 'AMS1117-3.3' },
      { mpn: 'NCP1117ST33T3G' },
      { mpn: 'AMS1117-3.3' },
      { mpn: ' NCP1117ST33T3G ' },
    ],
  })

  expect(matrixPrefill(link!.search)!.candidates.map((c) => c.mpn)).toEqual([
    'AMS1117-3.3', 'NCP1117ST33T3G',
  ])
})

test('nothing to show is no link at all, rather than one that opens on an error', () => {
  expect(matrixQuery({ affected, candidates: [] })).toBeNull()
  expect(matrixQuery({ affected: [], candidates: [{ mpn: 'AMS1117-3.3' }] })).toBeNull()
  expect(
    matrixQuery({ affected: [{ line_id: 'a', refdes: [] }], candidates: [{ mpn: 'X' }] }),
  ).toBeNull()
})

test('a half-filled query runs nothing', () => {
  expect(matrixPrefill('lines=a&slot=u1')).toBeNull()
  expect(matrixPrefill('lines=a&candidates=X')).toBeNull()
  expect(matrixPrefill('slot=u1&candidates=X')).toBeNull()
  expect(matrixPrefill('')).toBeNull()
})

test('a candidate carries who makes it, because the number alone names several parts', () => {
  const link = matrixQuery({
    affected,
    candidates: [
      { mpn: 'LD1117-3.3', manufacturer: 'UMW(Youtai Semiconductor Co., Ltd.)' },
      { mpn: 'TLV1117LV33DCYR', manufacturer: 'Texas Instruments' },
    ],
  })!

  // The separator is a pipe and not a comma: that manufacturer name contains commas, and a
  // comma-separated pair would split in the middle of a company.
  expect(matrixPrefill(link.search)!.manufacturers).toEqual({
    'LD1117-3.3': 'UMW(Youtai Semiconductor Co., Ltd.)',
    'TLV1117LV33DCYR': 'Texas Instruments',
  })
  expect(link.manufacturers['TLV1117LV33DCYR']).toBe('Texas Instruments')
})

test('a candidate with no recorded maker carries only its number', () => {
  const link = matrixQuery({ affected, candidates: [{ mpn: 'LD1117-3.3' }] })!

  expect(matrixPrefill(link.search)!.candidates).toEqual([{ mpn: 'LD1117-3.3' }])
  expect(link.manufacturers).toEqual({})
})

test('the same part under one maker appears once', () => {
  const link = matrixQuery({
    affected,
    candidates: [
      { mpn: 'TLV1117LV33DCYR', manufacturer: 'Texas Instruments' },
      { mpn: 'TLV1117LV33DCYR', manufacturer: 'Texas Instruments' },
    ],
  })!

  expect(matrixPrefill(link.search)!.candidates).toHaveLength(1)
})

test('a name survives the round trip through the query string', () => {
  const sent = { mpn: 'SPX1117M3-L-3-3/TR', manufacturer: 'MaxLinear' }
  const link = matrixQuery({ affected, candidates: [sent] })!

  expect(matrixPrefill(link.search)!.candidates).toEqual([sent])
})

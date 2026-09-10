import { describe, expect, test } from 'bun:test'

import { boardChangeCaption, cropBox, cropTreatment } from './BoardConsequence'

describe('board consequence evidence', () => {
  test('makes a true drop-in and the fitted-part identity explicit', () => {
    expect(boardChangeCaption({
      footprint: { from: 'SOT-223-3', to: 'SOT-223-3' },
      retiring: 'LM1117IMPX-3.3/NOPB',
      candidate: 'NCP1117ST33T3G',
    })).toBe(
      'FOOTPRINT: SOT-223-3 → SOT-223-3 (DROP-IN) · FITTED PART: LM1117IMPX-3.3/NOPB → NCP1117ST33T3G',
    )
  })

  test('covers the actual nonzero crop and uses a neutral change treatment', () => {
    expect(cropBox('104.2 52.5 18 18')).toEqual({ x: 104.2, y: 52.5, width: 18, height: 18 })
    expect(cropTreatment('before')).toEqual({ overlay: 'none', stroke: '#e5e7eb' })
    expect(cropTreatment('after', false)).toEqual({ overlay: '#a78bfa', stroke: '#c4b5fd' })
    expect(cropTreatment('after', true)).toEqual({ overlay: '#a78bfa', stroke: '#c4b5fd' })
  })
})

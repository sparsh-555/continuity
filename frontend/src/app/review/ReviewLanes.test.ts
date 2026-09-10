import { describe, expect, test } from 'bun:test'

import { checkLabel, fresh, withReviewFrame } from './ReviewLanes'

describe('company-wide review lanes', () => {
  test('keeps candidate narration and complete check verdicts for an expanded lane', () => {
    const candidate = withReviewFrame(fresh('line-1', 'Sensor node'), {
      type: 'candidate', seq: 1, line_id: 'line-1', slot: 'u1', part: { mpn: 'NCP1117ST33T3G' },
    })
    const checked = withReviewFrame(candidate, {
      type: 'check', seq: 2, line_id: 'line-1', slot: 'u1', rule: 'thermal_margin',
      scope: 'U1', status: 'satisfied', detail: '84 °C below limit', margin: '84 °C',
      departments: ['engineering'], accepted: false,
    })

    expect(checked.trace).toEqual([
      { kind: 'said', text: 'Trying NCP1117ST33T3G.' },
      {
        kind: 'check', rule: 'thermal_margin', scope: 'U1', status: 'satisfied',
        detail: '84 °C below limit', margin: '84 °C', departments: ['engineering'], accepted: false,
      },
    ])
    const check = checked.trace[1]
    if (check.kind !== 'check') throw new Error('expected a check')
    expect(checkLabel(check)).toBe('SATISFIED')
    expect(checkLabel({ ...check, status: 'failed', accepted: true })).toBe('ACCEPTED FAILURE')
  })
})

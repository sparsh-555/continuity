import { expect, test } from 'bun:test'

import { showsRestingStatement, slotsWith } from './ReviewTrace'
import type { LineCheck } from '../lib/api'

const check = (slots: LineCheck['slots']): LineCheck => ({
  slots,
  checked: 22,
  unresolved: [],
  not_assessed: [],
  evidence_missing: [],
})

const slot = (status: 'pass' | 'accepted' | 'conflict', accepted: string[] = []) => ({
  status,
  checked: 6,
  detail: status === 'pass' ? null : '1,133 in stock at JLCPCB, below the 5,000 minimum.',
  accepted,
})

test('a board nobody has reviewed states what the engine found', () => {
  expect(showsRestingStatement(0, 0)).toBe(true)
})

test('a trace displaces the resting statement, because it is the better account', () => {
  expect(showsRestingStatement(12, 0)).toBe(false)
})

test('an accepted failure survives the trace that predates the signature', () => {
  expect(showsRestingStatement(12, 1)).toBe(true)
})

test('the accepted slots are the ones a desk signed for, not the failing ones', () => {
  const board = check({
    u1: slot('accepted', ['availability']),
    u2: slot('pass'),
    c1: slot('conflict'),
  })

  expect(slotsWith(board, 'accepted').map(([refdes]) => refdes)).toEqual(['u1'])
  expect(slotsWith(board, 'conflict').map(([refdes]) => refdes)).toEqual(['c1'])
  expect(slotsWith(null, 'accepted')).toEqual([])
})

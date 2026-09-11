import { expect, test } from 'bun:test'

import {
  emptyLanes,
  fresh,
  hasSigned,
  lanesFromReview,
  pacedDelay,
  reduceFrame,
  replayFrames,
  seededLanes,
  withSignatures,
  type StoredNoticeReview,
} from './laneState'
import type { ReviewFrame } from '../lib/api'

const started = (lines: Array<[string, string]>): ReviewFrame => ({
  type: 'review_started', seq: 0, notice_id: 'n1', mpn: 'AMS1117-3.3',
  lines: lines.map(([line_id, name]) => ({ line_id, name })),
})

const said = (lineId: string | null, text: string, seq: number): ReviewFrame =>
  ({ type: 'reasoning', seq, line_id: lineId, slot: null, text })

const check = (lineId: string, rule: string, seq: number): ReviewFrame => ({
  type: 'check', seq, line_id: lineId, slot: 'u1', rule, scope: '3v3',
  status: 'satisfied', detail: '84 °C to spare', margin: '84 °C',
  departments: ['engineering'], accepted: false,
})

const done = (lineId: string, proposal: string, seq: number): ReviewFrame => ({
  type: 'line_done', seq, line_id: lineId, line_name: lineId, proposal,
  decision_id: 'd1', reason: 'clears every check', conditional: false, roles: ['engineering'],
})

const question = (lineId: string, seq: number): ReviewFrame => ({
  type: 'question', seq, line_id: lineId, question_id: 'decision:d1',
  text: 'NCP1117ST33T3G on the Sensor node. Approve the change?',
  suggestions: ['Approve and apply', 'Leave it'], roles: ['engineering', 'procurement'],
})

const liveRun = (): ReturnType<typeof reduceFrame> =>
  [started([['l1', 'Sensor node']]), said(null, 'AMS1117-3.3 is going end of life.', 1),
   check('l1', 'thermal_dissipation', 2), done('l1', 'NCP1117ST33T3G', 3)]
    .reduce(reduceFrame, emptyLanes)

const stored = (over: Partial<StoredNoticeReview> = {}): StoredNoticeReview => ({
  decision_id: 'd1', line_id: 'l1', line_name: 'Sensor node', state: 'approved',
  proposal: 'NCP1117ST33T3G', gate_rule: null, roles: ['engineering'],
  signed: [], outstanding: [],
  frames: [said(null, 'AMS1117-3.3 is going end of life.', 0),
           check('l1', 'thermal_dissipation', 1), done('l1', 'NCP1117ST33T3G', 2)],
  ...over,
})

test('a hydrated lane is the lane a live run produced', () => {
  const live = liveRun()
  const replayed = lanesFromReview([stored()])

  expect(replayed.lanes).toEqual(live.lanes)
  expect(replayed.preamble).toEqual(live.preamble)
})

test('a replay never claims to be running', () => {
  expect(lanesFromReview([stored()]).lanes[0].running).toBe(false)
})

test('a finished run reaches the same verdict word either way', () => {
  const live = liveRun().lanes[0]
  const replayed = lanesFromReview([stored()]).lanes[0]

  expect(replayed.proposal).toBe(live.proposal)
  expect(replayed.reason).toBe(live.reason)
  expect(replayed.trace).toEqual(live.trace)
})

test('a pending decision comes back with the question that was asked', () => {
  const rows = [stored({
    state: 'pending',
    frames: [...stored().frames, question('l1', 3)],
  })]

  const lane = lanesFromReview(rows).lanes[0]

  expect(lane.question).toEqual({
    decisionId: 'd1',
    text: 'NCP1117ST33T3G on the Sensor node. Approve the change?',
    roles: ['engineering', 'procurement'],
  })
})

test('who has signed survives the replay, and nobody having signed shows nothing', () => {
  const partial = lanesFromReview([stored({ state: 'pending', signed: ['engineering'],
                                           outstanding: ['procurement'] })])
  expect(partial.lanes[0].signatures).toEqual({ signed: ['engineering'], outstanding: ['procurement'] })

  const untouched = lanesFromReview([stored({ state: 'pending', signed: [], outstanding: ['engineering'] })])
  expect(untouched.lanes[0].signatures).toBeNull()
})

test('three boards hydrate as three lanes, each holding its own trace', () => {
  const rows = ['l1', 'l2', 'l3'].map((id) => stored({
    decision_id: `d-${id}`, line_id: id, line_name: id.toUpperCase(),
    frames: [said(null, 'retired', 0), check(id, 'availability', 1), done(id, `PART-${id}`, 2)],
  }))

  const state = lanesFromReview(rows)

  expect(state.lanes.map((lane) => lane.name)).toEqual(['L1', 'L2', 'L3'])
  expect(state.lanes.map((lane) => lane.proposal)).toEqual(['PART-l1', 'PART-l2', 'PART-l3'])
  expect(state.lanes[0].trace.filter((item) => item.kind === 'check')).toHaveLength(1)
})

test('an empty answer hydrates to nothing rather than to empty lanes', () => {
  expect(lanesFromReview([])).toEqual(emptyLanes)
})

test('a stale hydration does not overwrite a run that has already started', () => {
  // The guard is in the component, but the shape it relies on is this: an empty state is
  // untouched, and a state with lanes is not.
  const running = { ...emptyLanes, lanes: [fresh('l1', 'Sensor node')] }
  expect(running.lanes).toHaveLength(1)
})

test('a desk that has already signed is not offered the question again', () => {
  // The rule `/approvals` already holds, in the second place a question is answered. A desk
  // that signs twice is refused by the server, and before this the refusal was painted on the
  // lane as FAILED — a board that agrees with itself reading as a failed one.
  const lane = {
    ...fresh('l1', 'Sensor node'),
    signatures: { signed: ['engineering'], outstanding: ['procurement', 'quality'] },
  }

  expect(hasSigned(lane, ['engineering'])).toBe(true)
  expect(hasSigned(lane, ['procurement'])).toBe(false)
})

test('nobody has signed before anybody has signed', () => {
  expect(hasSigned(fresh('l1', 'Sensor node'), ['engineering', 'quality'])).toBe(false)
})

test('one person holding two desks is signed when either of them signed', () => {
  const lane = {
    ...fresh('l1', 'Sensor node'),
    signatures: { signed: ['quality'], outstanding: ['engineering'] },
  }

  expect(hasSigned(lane, ['engineering', 'quality'])).toBe(true)
})

test('a replay applies the run in the order the run emitted it', () => {
  // **The lanes are two recordings of one run.** Each decision keeps its own board's frames,
  // and every frame carries the run's `seq`, so sorting by it restores the interleaving the
  // live stream had. Playing lane by lane would show sequentially exactly what this product
  // exists to show happening at once.
  const sensor = stored({
    line_id: 'l1',
    frames: [said(null, 'the notice', 0), said('l1', 'board one, late', 5)],
  })
  const gateway = stored({
    line_id: 'l2',
    line_name: 'Gateway',
    frames: [said(null, 'the notice', 0), said('l2', 'board two, early', 2)],
  })

  const order = replayFrames([sensor, gateway]).map((frame) =>
    'text' in frame ? frame.text : frame.type,
  )

  expect(order).toEqual(['the notice', 'board two, early', 'board one, late'])
})

test('a paced replay ends exactly where an instant one does', () => {
  // The pacing must change when the frames arrive and nothing else. This is the guard: the
  // same frames, in the same order, through the same reducer, one at a time.
  const rows = [stored(), stored({ line_id: 'l2', line_name: 'Gateway', signed: ['engineering'] })]

  const paced = withSignatures(
    replayFrames(rows).reduce(reduceFrame, seededLanes(rows)),
    rows,
  )

  expect(paced).toEqual(lanesFromReview(rows))
})

test('the pace is staggered rather than metronomic', () => {
  // A fixed interval reads as a machine printing lines, and the run being played back was
  // not evenly spaced. Bounded and repeatable, because a jitter nobody can test is a jitter
  // nobody can reason about.
  const delays = [0, 1, 2, 3, 4, 5, 6, 7].map((position) => pacedDelay(position))

  expect(new Set(delays).size).toBeGreaterThan(3)
  expect(Math.min(...delays)).toBeGreaterThanOrEqual(150)
  expect(Math.max(...delays)).toBeLessThanOrEqual(240)
})

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import { formatFirstBallWire, readFirstBallAck } from './firstBallWire'
import { parseD1AckEnvelope } from '../lib/sync/ackEnvelope'
const fixture = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../backend/tests/fixtures/first_ball_payload_vectors_v1.json',
    ),
    'utf8',
  ),
).cases[0]
const payload = JSON.parse(fixture.v7Json)
function format(p = payload) {
  return formatFirstBallWire(
    p.calculation.request,
    p.calculation.response,
    p.observations,
    p.participants,
  )
}
it('既backend formatterの全値V7/V8と一致する', () => {
  const out = format()
  expect(out.payload).toEqual(payload)
  expect(out.stateDiff).toEqual(JSON.parse(fixture.v8Json))
  expect(out.payload.calculation.artifactSha256).toBe(artifactIdentity.sha256)
  payload.observations.course.x = '132'
  expect(out.payload.observations.course).toEqual(
    JSON.parse(fixture.v7Json).observations.course,
  )
})
describe('閉値codec', () => {
  it.each(['formatVersion', 'observations', 'participants', 'calculation'])(
    'fixture部材%sの余剰を拒否する',
    (section) => {
      const input = JSON.parse(fixture.v7Json)
      if (section === 'formatVersion') {
        input.calculation.response.ok = false
      } else if (section === 'calculation') {
        input.calculation.response.value.t1.extra = true
      } else input[section].extra = true
      expect(() => format(input)).toThrow()
    },
  )
  it.each(['t1', 't2'])('計算応答%sの欠落を拒否する', (key) => {
    const p = JSON.parse(fixture.v7Json)
    delete p.calculation.response.value[key]
    expect(() => format(p)).toThrow()
  })
  it('UUID/座標/欠測確認の不整合を拒否する', () => {
    for (const change of [
      (p: typeof payload) => {
        p.participants.batterId = 'not-uuid'
      },
      (p: typeof payload) => {
        p.observations.course.x = '264'
      },
      (p: typeof payload) => {
        p.observations.pitchSpeed = { kmh: null, outsideRangeConfirmed: true }
      },
    ]) {
      const p = JSON.parse(fixture.v7Json)
      change(p)
      expect(() => format(p)).toThrow()
    }
  })
})
const key = {
  d4: 'd4.1.test',
  d1: 1,
  d5: '11111111-1111-4111-8111-111111111111',
}
function ack(state = '受理') {
  return { advancedD3: 1, eventResults: [{ ...key, a5Result: state }] }
}
it('実wireの単一受理を既ACK adapter形へ写す', () => {
  const wire = ack()
  const read = readFirstBallAck(wire, key)!
  expect(read.envelope).toEqual(wire)
  expect(read.boundaryResult).toBe('B1')
  expect(parseD1AckEnvelope(read.envelope).eventResults[0]!.a5Result.id).toBe(
    '受理',
  )
})
it('未知/拒否ACK・slot/前進/余剰の不整合を成功にしない', () => {
  for (const wire of [
    ack('未知'),
    ack('拒否'),
    ack('重複'),
    { ...ack(), advancedD3: 2 },
    { ...ack(), extra: true },
    {
      advancedD3: 1,
      eventResults: [{ ...key, d5: 'other', a5Result: '受理' }],
    },
    null,
  ])
    expect(readFirstBallAck(wire, key)).toBeUndefined()
})

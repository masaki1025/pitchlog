import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  formatOrdinaryPitchWire,
  isOrdinaryContinuationRequest,
  isOrdinaryContinuationSuccess,
  OrdinaryPitchWireError,
} from './ordinaryPitchWire'
const cases = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary37_continuation_candidate_v1.json',
    ),
    'utf8',
  ),
).cases
const observation = {
  pitchTypeKey: '実tenant球種',
  course: { unit: '1/263' as const, x: '132', y: '131' },
  pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
  stance: null,
  battingSide: null,
}
const participants = {
  batterId: '11111111-1111-4111-8111-111111111111',
  pitcherId: '22222222-2222-4222-8222-222222222222',
  catcherId: '33333333-3333-4333-8333-333333333333',
  battingOrder: '1',
}
describe('ordinary V7/V8閉codec', () => {
  it('候補20requestを補修せず読み、成功10件の計算全封筒/今回差分を完全保持する', () => {
    expect(cases).toHaveLength(20)
    const success = cases.filter(
      (row: { expected: { response: { ok: boolean } } }) =>
        row.expected.response.ok,
    )
    expect(success).toHaveLength(10)
    for (const row of cases)
      expect(isOrdinaryContinuationRequest(row.request), row.caseId).toBe(true)
    for (const row of success) {
      const response = row.expected.response
      expect(isOrdinaryContinuationSuccess(response)).toBe(true)
      const wire = formatOrdinaryPitchWire(row.request, response, observation, {
        ...participants,
        battingOrder: row.request.t1.before.stateFields['state.battingOrder'],
      })
      expect(wire.payload.calculation.request).toEqual(row.request)
      expect(wire.payload.calculation.response).toEqual(response)
      expect(wire.stateDiff).toEqual(response.value.newHistoryEntry.difference)
      expect(wire.payload).toEqual({
        formatVersion: 'ordinary-pitch-play-v1',
        observations: observation,
        participants: {
          ...participants,
          battingOrder: row.request.t1.before.stateFields['state.battingOrder'],
        },
        calculation: {
          formatVersion: 'ordinary-pitch-calculation-v1',
          artifactSha256: wire.payload.calculation.artifactSha256,
          request: row.request,
          response,
        },
      })
      expect(wire.payload.calculation.artifactSha256).toMatch(/^[0-9a-f]{64}$/)
      expect(wire.payload.calculation.response.value.t1).not.toHaveProperty(
        'historyContext',
      )
      expect(
        Object.hasOwn(wire.stateDiff.stateFields, 'state.count.strikes'),
      ).toBe(
        Object.hasOwn(
          response.value.newHistoryEntry.difference.stateFields,
          'state.count.strikes',
        ),
      )
    }
  })
  it('欠落optional差分をnullや余剰キーで補わず、拒否応答を成功化しない', () => {
    const row = cases[0],
      response = structuredClone(row.expected.response)
    response.value.newHistoryEntry.difference.stateFields[
      'state.count.strikes'
    ] = null
    expect(isOrdinaryContinuationSuccess(response)).toBe(false)
    for (const bad of [
      row.expected.response.value,
      { ...row.expected.response, extra: true },
      {
        ok: true,
        value: { ...row.expected.response.value, historyContext: [] },
      },
      cases[10].expected.response,
    ])
      expect(() =>
        formatOrdinaryPitchWire(row.request, bad, observation, participants),
      ).toThrow(OrdinaryPitchWireError)
  })
  it('scope/ref/contentの付替えと不正観測/参加者を拒否する', () => {
    const row = cases[0]
    const response = structuredClone(row.expected.response)
    response.value.nextPrefixRef.length = '9'
    expect(() =>
      formatOrdinaryPitchWire(row.request, response, observation, participants),
    ).toThrow(OrdinaryPitchWireError)
    for (const p of [
      { ...participants, battingOrder: '0' },
      { ...participants, batterId: 'x' },
      { ...participants, extra: true },
    ])
      expect(() =>
        formatOrdinaryPitchWire(
          row.request,
          row.expected.response,
          observation,
          p,
        ),
      ).toThrow(OrdinaryPitchWireError)
    for (const o of [
      { ...observation, course: { ...observation.course, x: '264' } },
      { ...observation, course: { ...observation.course, x: '01' } },
      { ...observation, pitchTypeKey: '' },
      {
        ...observation,
        pitchSpeed: { kmh: null, outsideRangeConfirmed: true },
      },
    ])
      expect(() =>
        formatOrdinaryPitchWire(
          row.request,
          row.expected.response,
          o,
          participants,
        ),
      ).toThrow(OrdinaryPitchWireError)
  })
})

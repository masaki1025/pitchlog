// @vitest-environment node
import { describe, expect, it } from 'vitest'
import canonical from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import prefixCases from '../../../contracts/state-transition/batted_hit_prefix_cases_v1.json'
import { lineupPrefixSpikeSchema } from './lineupPrefixSpikeSchema'
import { isClosedPlaySchema } from './terminalPitchWire'

const caseRequest = prefixCases.cases[0]!.request as {
  t1: { before: Record<string, unknown> }
}
const before = caseRequest.t1.before
const caseT1 = (
  prefixCases.cases[0]!.expected as {
    value: { t1: Record<string, unknown> }
  }
).value.t1

function applied(overrides: Array<Record<string, string>>) {
  return { kind: 'applied', overrides }
}

function t1Request(runnerAdvanceOverrides: unknown) {
  return {
    eventKind: 'batting-result',
    resultId: 'batting-result.single',
    pitchEventKind: 'pitch-event',
    before,
    officialScoringPayload: 'no-error',
    interferenceRuling: 'not-required',
    runnerAdvanceOverrides,
    thirdOutObservation: 'none',
  }
}

describe('正式候補schemaは原値を書き換えず厳格に検証する', () => {
  it('SO-04のK3を正式候補が受理し、未知結果を拒否する', () => {
    const pitch = {
      eventKind: 'batting-result',
      resultId: 'batting-result.k3',
      pitchEventKind: 'pitch-event',
      before,
    }
    expect(isClosedPlaySchema(pitch, canonical, 'PitchT1Input')).toBe(true)
    expect(
      isClosedPlaySchema(pitch, lineupPrefixSpikeSchema, 'PitchT1Input'),
    ).toBe(true)
    expect(
      isClosedPlaySchema(
        { ...pitch, resultId: 'batting-result.unknown' },
        lineupPrefixSpikeSchema,
        'PitchT1Input',
      ),
    ).toBe(false)
  })
  it('SO-05の固定2アウトを受理し、対象欠落や3アウトを拒否する', () => {
    const value = structuredClone(caseT1)
    value.outEffect = {
      count: '2',
      targets: ['batter', { runner: '1' }],
    }
    expect(isClosedPlaySchema(value, canonical, 'T1')).toBe(true)
    expect(isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'T1')).toBe(true)
    for (const outEffect of [
      { count: '2', targets: ['batter'] },
      { count: '2', targets: ['batter', { runner: '2' }] },
      { count: '3', targets: ['batter', { runner: '1' }] },
    ])
      expect(
        isClosedPlaySchema(
          { ...value, outEffect },
          lineupPrefixSpikeSchema,
          'T1',
        ),
      ).toBe(false)
  })
  it('正式候補はappliedを受理する', () => {
    const value = t1Request(applied([{ runnerBase: '1', destination: '3' }]))
    expect(isClosedPlaySchema(value, canonical, 'BattedHitT1Input')).toBe(true)
    expect(
      isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'BattedHitT1Input'),
    ).toBe(true)
  })
  it('正式候補はforced/optional到達塁を受理する', () => {
    const value = structuredClone(caseT1)
    value.runnerDefaultAdvance = {
      first: { modality: 'forced', destination: '3' },
      second: { modality: 'not-applicable', destination: null },
      third: { modality: 'not-applicable', destination: null },
    }
    expect(isClosedPlaySchema(value, canonical, 'T1')).toBe(true)
    expect(isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'T1')).toBe(true)
  })
  it('3走者までの閉形を受理し、4件目・未知到達塁・余剰fieldを拒否する', () => {
    expect(
      isClosedPlaySchema(
        t1Request(
          applied([
            { runnerBase: '1', destination: '4' },
            { runnerBase: '2', destination: '4' },
            { runnerBase: '3', destination: '4' },
          ]),
        ),
        lineupPrefixSpikeSchema,
        'BattedHitT1Input',
      ),
    ).toBe(true)
    for (const overrides of [
      [
        { runnerBase: '1', destination: '3' },
        { runnerBase: '2', destination: '4' },
        { runnerBase: '3', destination: '4' },
        { runnerBase: '1', destination: '4' },
      ],
      [{ runnerBase: '4', destination: '4' }],
      [{ runnerBase: '1', destination: '1' }],
      [{ runnerBase: '1', destination: '3', extra: 'x' }],
    ])
      expect(
        isClosedPlaySchema(
          t1Request(applied(overrides)),
          lineupPrefixSpikeSchema,
          'BattedHitT1Input',
        ),
      ).toBe(false)
  })
  it('検証は入力も正式候補schemaも変更しない', () => {
    const value = t1Request(applied([{ runnerBase: '1', destination: '3' }]))
    const snapshot = structuredClone(value)
    const schemaSnapshot = structuredClone(canonical)
    expect(
      isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'BattedHitT1Input'),
    ).toBe(true)
    expect(value).toEqual(snapshot)
    expect(canonical).toEqual(schemaSnapshot)
    expect(lineupPrefixSpikeSchema).toBe(canonical)
  })
  it('凡打死の明示OUT3だけを候補に加え、未知結果と未知第3アウトは拒否する', () => {
    const out = {
      ...t1Request('not-applied'),
      resultId: 'batting-result.batted-out',
      before: {
        ...before,
        stateFields: {
          ...(before.stateFields as Record<string, unknown>),
          'state.outs': '2',
          'state.runners': 'empty',
        },
      },
      thirdOutObservation: 'batter-before-first',
    }
    expect(isClosedPlaySchema(out, canonical, 'BattedHitT1Input')).toBe(true)
    expect(
      isClosedPlaySchema(out, lineupPrefixSpikeSchema, 'BattedHitT1Input'),
    ).toBe(true)
    expect(
      isClosedPlaySchema(
        { ...out, thirdOutObservation: 'force' },
        lineupPrefixSpikeSchema,
        'BattedHitT1Input',
      ),
    ).toBe(false)
    const oldHit = structuredClone(caseRequest) as Record<string, unknown>
    oldHit.t1 = {
      ...t1Request('not-applied'),
      thirdOutObservation: 'batter-before-first',
    }
    expect(isClosedPlaySchema(oldHit, lineupPrefixSpikeSchema, 'Request')).toBe(
      false,
    )
  })
})

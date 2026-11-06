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

describe('spike候補schemaは原値を書き換えず厳格に検証する', () => {
  it('SO-04のK3だけを既投球入力へ追加し、旧正準の結果集合を保つ', () => {
    const pitch = {
      eventKind: 'batting-result',
      resultId: 'batting-result.k3',
      pitchEventKind: 'pitch-event',
      before,
    }
    expect(isClosedPlaySchema(pitch, canonical, 'PitchT1Input')).toBe(false)
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
  it('SO-05の固定2アウトだけを候補T1へ追加し、対象欠落や3アウトを拒否する', () => {
    const value = structuredClone(caseT1)
    value.outEffect = {
      count: '2',
      targets: ['batter', { runner: '1' }],
    }
    expect(isClosedPlaySchema(value, canonical, 'T1')).toBe(false)
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
  it('canonical schemaはappliedを拒否し、spike schemaだけが受理する', () => {
    const value = t1Request(applied([{ runnerBase: '1', destination: '3' }]))
    expect(isClosedPlaySchema(value, canonical, 'BattedHitT1Input')).toBe(false)
    expect(
      isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'BattedHitT1Input'),
    ).toBe(true)
  })
  it('canonical schemaはforced/optional到達塁を拒否し、spike schemaだけが受理する', () => {
    const value = structuredClone(caseT1)
    value.runnerDefaultAdvance = {
      first: { modality: 'forced', destination: '3' },
      second: { modality: 'not-applicable', destination: null },
      third: { modality: 'not-applicable', destination: null },
    }
    expect(isClosedPlaySchema(value, canonical, 'T1')).toBe(false)
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
  it('検証は入力を書き換えず、canonical schemaの原値も変更しない', () => {
    const value = t1Request(applied([{ runnerBase: '1', destination: '3' }]))
    const snapshot = structuredClone(value)
    expect(
      isClosedPlaySchema(value, lineupPrefixSpikeSchema, 'BattedHitT1Input'),
    ).toBe(true)
    expect(value).toEqual(snapshot)
    const canonicalDefinitions = canonical.$defs as unknown as Record<
      string,
      { properties: { runnerAdvanceOverrides: unknown } }
    >
    expect(
      canonicalDefinitions.BattedHitT1Input.properties.runnerAdvanceOverrides,
    ).toEqual({ const: 'not-applied' })
  })
})

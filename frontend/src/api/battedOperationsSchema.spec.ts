// @vitest-environment node
/** 最終共有schemaを実製品JS matcherへ通す。補助の代替validatorを作らない。 */
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import schema from '../../../contracts/state-transition/lineup_play_prefix_schema_v1.json'
import payload from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import { isClosedPlaySchema } from './terminalPitchWire'
import domainIdentity from '../../public/domain/pitchlog-domain.json'
const cases = JSON.parse(
  readFileSync(
    new URL(
      '../../../backend/tests/fixtures/batted_operations_schema_cases_v1.json',
      import.meta.url,
    ),
    'utf8',
  ),
) as Array<{
  id: string
  t1: unknown
  observations: unknown
  t1Valid: boolean
  observationsValid: boolean
}>
it.each(cases)('$id の元値を構造検査し、補修しない', (row) => {
  const original = structuredClone(row)
  for (const document of [schema, payload])
    expect(isClosedPlaySchema(row.t1, document, 'BattedHitT1Input')).toBe(
      row.t1Valid,
    )
  expect(
    isClosedPlaySchema(row.observations, payload, 'BattedHitObservations'),
  ).toBe(row.observationsValid)
  expect(row).toEqual(original)
})
it('新しい定義には実JS matcherが無視するkeywordを置かない', () => {
  const names = [
    'BattedHitT1Input',
    'BattedRbiRulingByRunner',
    'BattedForceOutRunner',
    'LegacyWireHead',
    'RunnerWireHead',
    'BattedRbiWireHead',
    'WireHead',
  ]
  for (const document of [schema, payload])
    for (const name of names) {
      const serialized = JSON.stringify(
        (document.$defs as Record<string, unknown>)[name],
      )
      for (const keyword of [
        'if',
        'then',
        'else',
        'not',
        'minProperties',
        'contains',
        'prefixItems',
      ])
        expect(serialized).not.toContain(`"${keyword}":`)
      expect(serialized).not.toContain('"type":"integer"')
    }
})

import { runInNewContext } from 'node:vm'
import { webcrypto } from 'node:crypto'
import { beforeEach, afterEach, vi } from 'vitest'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type { BattedHitObservations } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import {
  isLineupDefinition,
  lineupWireHead,
  sealLineupMetadata,
  formatLineupPrefixWire,
} from './lineupPrefixWire'
const runtimeInputs = JSON.parse(
  readFileSync(
    new URL(
      '../../../backend/tests/fixtures/batted_operations_schema_runtime_requests_v1.json',
      import.meta.url,
    ),
    'utf8',
  ),
) as { samples: Array<{ operation: string; request: unknown }> }
const domain = runInNewContext(
  readFileSync(
    new URL('../../public/domain/pitchlog-domain.js', import.meta.url),
    'utf8',
  ) + ';PitchlogDomain',
) as { deriveLineupPlayPrefixWithContinuation: (input: string) => string }
beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => vi.unstubAllGlobals())
it.each(runtimeInputs.samples)(
  '$operation の実artifact応答をhead/封印/V7/V8へ接続する',
  async (row) => {
    const request = structuredClone(row.request) as {
      source: { executionArtifactSha256: string }
    }
    request.source.executionArtifactSha256 = domainIdentity.sha256
    const response: unknown = JSON.parse(
      domain.deriveLineupPlayPrefixWithContinuation(JSON.stringify(request)),
    )
    if (
      !isLineupDefinition<Request>(request, 'Request') ||
      !isLineupDefinition<Success>(response, 'Success')
    )
      throw new Error('実artifactの閉要求/成功応答ではない')
    const sealed = await sealLineupMetadata(request, response)
    const head = lineupWireHead(sealed.request, sealed.response)
    expect(isClosedPlaySchema(head, schema, 'WireHead')).toBe(true)
    if ('rbiRulingByRunner' in head) {
      for (const key of ['rbiRulingByRunner', 'runnerScoreEffects'])
        expect(
          isClosedPlaySchema(
            Object.fromEntries(Object.entries(head).filter(([k]) => k !== key)),
            schema,
            'WireHead',
          ),
        ).toBe(false)
    }
    const t = sealed.request.t1
    if (!('runnerAdvanceOverrides' in t) || !('officialScoringPayload' in t))
      throw new Error('打球実入力ではない')
    const observed: unknown = {
      pitchTypeKey: 'fixture.fastball',
      course: { unit: '1/263', x: '132', y: '131' },
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
      resultId: t.resultId,
      battedBall: {
        typeKey: null,
        strengthKey: null,
        hitX: null,
        hitY: null,
        rawFielderPosition: null,
        resolvedFielderId: null,
      },
      officialScoringPayload:
        t.officialScoringPayload === 'error-recorded'
          ? {
              kind: 'error-recorded',
              errors: [
                {
                  fielder: {
                    kind: 'official',
                    player_id: sealed.request.source.participants.pitcherId,
                  },
                  count: 1,
                },
              ],
            }
          : { kind: 'no-error', errorCount: '0', fielders: [] },
      interferenceRuling: { kind: 'not-required' },
      runnerAdvanceOverridesByRunner:
        t.runnerAdvanceOverrides === 'not-applied'
          ? { kind: 'not-applied', overrides: [] }
          : t.runnerAdvanceOverrides,
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
      ...('rbiRulingByRunner' in t
        ? { rbiRulingByRunner: t.rbiRulingByRunner }
        : {}),
      ...('outRunner' in t ? { outRunner: t.outRunner } : {}),
    }
    if (
      !isClosedPlaySchema<BattedHitObservations>(
        observed,
        payload,
        'BattedHitObservations',
      )
    )
      throw new Error('公式観測の閉形ではない')
    const value = await formatLineupPrefixWire(
      sealed.request,
      sealed.response,
      observed,
      sealed.response.value.beforeParticipants,
    )
    expect(isClosedPlaySchema(value.payload, payload)).toBe(true)
    expect(value.stateDiff).toEqual(
      sealed.response.value.newHistoryEntry.difference,
    )
  },
)

it.each([
  'run',
  'rbi',
  'allowed',
  'score',
  'family',
  'overrides',
  'extra-effect',
  'forged-rbi',
])('空effectで%sを偽装しても封印しない', (fault) => {
  const sample = runtimeInputs.samples.find((r) => r.operation === 'batted-out')
  if (!sample) throw new Error('実hold入力がない')
  const q = structuredClone(sample.request) as Record<
    string,
    Record<string, unknown>
  >
  const r = JSON.parse(
    domain.deriveLineupPlayPrefixWithContinuation(JSON.stringify(q)),
  ) as {
    value: {
      t1: {
        statFlags: Record<string, unknown>
        after: { stateFields: Record<string, unknown> }
      }
      runnerScoreEffects: unknown[]
    }
  }
  if (fault === 'run' || fault === 'rbi' || fault === 'allowed')
    r.value.t1.statFlags[{ run: '得点', rbi: '打点', allowed: '失点' }[fault]] =
      true
  else if (fault === 'score')
    r.value.t1.after.stateFields['state.score'] = { away: '999', home: '0' }
  else if (fault === 'family') q.t1!.resultId = 'batting-result.single'
  else if (fault === 'overrides') q.t1!.runnerAdvanceOverrides = 'not-applied'
  else if (fault === 'forged-rbi')
    q.t1!.rbiRulingByRunner = { '1': 'ordinary-play' }
  else {
    const scoring = runtimeInputs.samples.find(
      (r) => r.operation === 'sacrifice-fly',
    )
    if (!scoring) throw new Error('実SF入力がない')
    r.value.runnerScoreEffects = JSON.parse(
      domain.deriveLineupPlayPrefixWithContinuation(
        JSON.stringify(scoring.request),
      ),
    ).value.runnerScoreEffects
  }
  expect(() => {
    if (
      !isLineupDefinition<Request>(q, 'Request') ||
      !isLineupDefinition<Success>(r, 'Success')
    )
      throw new Error('元型拒否')
    lineupWireHead(q, r)
  }).toThrow()
})

import legacyInputs from './fixtures/currentLineupPrefixPayload.v1.json'
it('旧32field headは全34行でbyteに対応する全値を変えない', () => {
  for (const sample of legacyInputs.cases) {
    const q: unknown = sample.V7.calculation.request
    const r: unknown = sample.V7.calculation.response
    if (
      !isLineupDefinition<Request>(q, 'Request') ||
      !isLineupDefinition<Success>(r, 'Success')
    )
      throw new Error('旧元型拒否')
    const head = lineupWireHead(q, r)
    expect(head).toEqual(sample.wireHead)
    expect(isClosedPlaySchema(head, schema, 'WireHead')).toBe(true)
  }
})

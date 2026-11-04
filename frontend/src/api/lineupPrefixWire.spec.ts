// @vitest-environment node
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import vectors from '../../../contracts/state-transition/lineup_play_prefix_payload_vectors_v1.json'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type {
  Observations,
  Participants,
} from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import {
  formatLineupPrefixWire,
  lineupWireHead,
  isLineupDefinition,
} from './lineupPrefixWire'
import { playHash } from './terminalPitchWire'
beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => vi.unstubAllGlobals())
it('正式34例の32field/wireSHA/V7/V8全値をそのまま照合する', async () => {
  expect(vectors.cases).toHaveLength(34)
  for (const row of vectors.cases) {
    const p = row.V7
    const q = p.calculation.request as Request,
      r = p.calculation.response as unknown as Success
    expect(lineupWireHead(q, r)).toEqual(row.wireHead)
    expect(await playHash(lineupWireHead(q, r))).toBe(row.wireDigest)
    expect(
      await formatLineupPrefixWire(
        q,
        r,
        p.observations as Observations,
        p.participants as Participants,
      ),
    ).toEqual({ payload: p, stateDiff: row.V8 })
  }
})
it.each([
  'missing',
  'extra',
  'cursor',
  'scope',
  'ref',
  'participants',
  'provenance',
  'history',
  'artifact',
])('未知/欠測/関連改変%sを閉拒否する', async (kind) => {
  const q = structuredClone(vectors.cases[0]!.V7.calculation.request) as Request
  const r = structuredClone(
    vectors.cases[0]!.V7.calculation.response,
  ) as unknown as Success
  if (kind === 'missing') {
    const incomplete = structuredClone(q) as unknown as {
      source: Record<string, unknown>
    }
    delete incomplete.source.participants
    expect(isLineupDefinition(incomplete, 'Request')).toBe(false)
    return
  }
  if (kind === 'extra') {
    expect(isLineupDefinition({ ...q, unknown: true }, 'Request')).toBe(false)
    return
  }
  if (kind === 'cursor') {
    expect(
      isLineupDefinition(
        {
          ...q,
          t1: {
            ...q.t1,
            before: {
              ...q.t1.before,
              battingOrderBySide: { away: '0', home: '1' },
            },
          },
        },
        'Request',
      ),
    ).toBe(false)
    return
  }
  const bad = JSON.parse(JSON.stringify(r)) as unknown as Success
  if (kind === 'scope')
    Object.assign(bad.value.nextPrefixRef, { scope: 'play-prefix-v2' })
  if (kind === 'ref')
    Object.assign(bad.value.previousPrefixRef, { length: '999' })
  if (kind === 'participants')
    Object.assign(bad.value.beforeParticipants, {
      catcherId: q.source.participants.pitcherId,
    })
  if (kind === 'provenance')
    Object.assign(q.source.provenance, { unknown: true })
  if (kind === 'history')
    Object.assign(bad.value.newHistoryEntry.difference, { unknown: true })
  if (kind === 'artifact')
    Object.assign(bad.value, { executionArtifactSha256: '0'.repeat(64) })
  await expect(
    formatLineupPrefixWire(
      q,
      bad,
      vectors.cases[0]!.V7.observations as Observations,
      vectors.cases[0]!.V7.participants as Participants,
    ),
  ).rejects.toThrow()
})

import hitVectors from '../../../contracts/state-transition/batted_hit_prefix_cases_v1.json'
import { sealLineupMetadata } from './lineupPrefixWire'
import type { BattedHitObservations } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
it('先置き19手例を全12観測と対応結果へ束縛し、相関違反を拒否する', async () => {
  expect(hitVectors.cases).toHaveLength(19)
  for (const row of hitVectors.cases) {
    const q = row.request as Request,
      r = row.expected as unknown as Success
    const sealed = await sealLineupMetadata(q, r)
    const observations: BattedHitObservations = {
      pitchTypeKey: 'observed.pitch',
      course: { unit: '1/263', x: '1', y: '263' },
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
      resultId: q.t1.resultId as BattedHitObservations['resultId'],
      battedBall: {
        typeKey: null,
        strengthKey: null,
        hitX: null,
        hitY: null,
        rawFielderPosition: null,
        resolvedFielderId: null,
      },
      officialScoringPayload: {
        kind: 'no-error',
        errorCount: '0',
        fielders: [],
      },
      interferenceRuling: { kind: 'not-required' },
      runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
      thirdOutObservation: { kind: 'none' },
      thirdOutTimingByRunner: {},
    }
    const actual = await formatLineupPrefixWire(
      sealed.request,
      sealed.response,
      observations,
      q.source.participants,
    )
    expect(actual.payload.observations).toEqual(observations)
    expect(actual.payload.calculation.request).toEqual(sealed.request)
    expect(actual.payload.calculation.response).toEqual(sealed.response)
    expect(actual.stateDiff).toEqual(r.value.newHistoryEntry.difference)
    await expect(
      formatLineupPrefixWire(
        sealed.request,
        sealed.response,
        {
          ...observations,
          resultId:
            q.t1.resultId === 'batting-result.single'
              ? 'batting-result.home-run'
              : 'batting-result.single',
        },
        q.source.participants,
      ),
    ).rejects.toThrow()
    await expect(
      formatLineupPrefixWire(
        sealed.request,
        sealed.response,
        {
          ...observations,
          battedBall: { ...observations.battedBall, hitX: '-0.00001' },
        },
        q.source.participants,
      ),
    ).rejects.toThrow()
    const old = {
      pitchTypeKey: observations.pitchTypeKey,
      course: observations.course,
      pitchSpeed: observations.pitchSpeed,
      stance: null,
      battingSide: null,
    }
    await expect(
      formatLineupPrefixWire(
        sealed.request,
        sealed.response,
        old,
        q.source.participants,
      ),
    ).rejects.toThrow()
  }
})

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

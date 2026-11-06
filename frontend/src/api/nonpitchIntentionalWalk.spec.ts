import { expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import identity from '../../public/domain/pitchlog-domain.json'
import schema from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import { domainOperations } from '../domain/publicApi'
import { isClosedPlaySchema } from './terminalPitchWire'
import {
  formatLineupPrefixWire,
  isLineupSpikeDefinition,
  sealLineupMetadata,
} from './lineupPrefixWire'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type { LineupPlayPrefixV7 } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'

function request(): Request {
  const vectors = JSON.parse(
    readFileSync(
      resolve('../contracts/state-transition/lineup_play_prefix_cases_v1.json'),
      'utf8',
    ),
  ) as { cases: Array<{ caseId: string; request: Record<string, unknown> }> }
  const original = vectors.cases.find(
    (item) => item.caseId === 'V3-STRIKEOUT-1-B1-O2',
  )
  expect(original).toBeDefined()
  const q = structuredClone(original!.request)
  const t1 = q.t1 as Record<string, unknown>
  const source = q.source as Record<string, unknown>
  for (const state of [
    (t1.before as Record<string, unknown>).stateFields,
    (source.after as Record<string, unknown>).stateFields,
  ] as Array<Record<string, unknown>>) {
    state['state.count.strikes'] = '0'
    state['state.count.balls'] = '0'
    state['state.outs'] = '0'
  }
  ;((source.t2 as Record<string, unknown>).facts as Record<string, unknown>)[
    'afterOuts'
  ] = '0'
  source.executionArtifactSha256 = identity.sha256
  t1.resultId = 'batting-result.intentional-walk'
  t1.pitchEventKind = 'non-pitch-event'
  expect(isLineupSpikeDefinition<Request>(q, 'Request')).toBe(true)
  return q as Request
}

it('閉契約から申告敬遠を唯一核で評価し、V7/V8へ全値保存する', async () => {
  const q = request()
  const response = JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(JSON.stringify(q)),
  ) as Success
  expect(response.ok).toBe(true)
  const sealed = await sealLineupMetadata(q, response)
  const wire = await formatLineupPrefixWire(
    sealed.request,
    sealed.response,
    { kind: 'intentional-walk' },
    sealed.response.value.beforeParticipants,
  )
  expect(wire.payload.observations).toEqual({ kind: 'intentional-walk' })
  expect(wire.payload.calculation.artifactSha256).toBe(identity.sha256)
  expect(wire.stateDiff).toEqual(
    sealed.response.value.newHistoryEntry.difference,
  )
  expect(isClosedPlaySchema<LineupPlayPrefixV7>(wire.payload, schema)).toBe(
    true,
  )
})

it('旧投球枝は保持し、余剰/欠落/偽投球/未知非投球を拒否する', () => {
  const q = request() as unknown as Record<string, unknown>
  const t1 = q.t1 as Record<string, unknown>
  for (const mutation of [
    { ...t1, resultId: 'batting-result.unknown' },
    { ...t1, pitchEventKind: 'pitch-event' },
    { ...t1, extra: true },
    { ...t1, resultId: undefined },
  ])
    expect(isLineupSpikeDefinition({ ...q, t1: mutation }, 'Request')).toBe(
      false,
    )
})

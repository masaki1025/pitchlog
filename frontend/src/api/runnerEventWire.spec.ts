// @vitest-environment node
import { webcrypto } from 'node:crypto'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import authored from '../../../docs/features/mvp-runner-operations-connection/candidate-cases.json'
import identity from '../../public/domain/pitchlog-domain.json'
import {
  isRunnerRequest,
  isRunnerSuccess,
  formatRunnerEventWire,
} from './runnerEventWire'
import {
  formatLineupPrefixWire,
  lineupWireHead,
  sealLineupMetadata,
} from './lineupPrefixWire'
import { playHash } from './terminalPitchWire'

beforeEach(() => vi.stubGlobal('crypto', webcrypto))
afterEach(() => vi.unstubAllGlobals())
/** 作者の構造候補を現行pin封筒で検査するだけ。数学/実host/認可を証明しない。 */
async function metadataCase(index: number) {
  const original = authored.cases[index]!
  const q = JSON.parse(JSON.stringify(original.request))
  const r = JSON.parse(JSON.stringify(original.expected))
  // 過去source/priorArtifactを変えず、この新しい構造テストだけの実行宣言を束縛する。
  q.source.executionArtifactSha256 = identity.sha256
  r.value.executionArtifactSha256 = identity.sha256
  if (!isRunnerRequest(q) || !isRunnerSuccess(r))
    throw new Error('新閉型の固定候補が不一致')
  return sealLineupMetadata(q, r)
}
for (let index = 0; index < authored.cases.length; index++)
  it(`新RunnerV7 ${index}は同原値と固定封印のまま旧共通formatterからも出力できる`, async () => {
    const { request: q, response: r } = await metadataCase(index)
    const p = q.t1.runnerObservation
    const observations =
      q.t1.pitchEventKind === 'non-pitch-event'
        ? { kind: 'non-pitch-event' as const, runnerObservation: p }
        : {
            pitchTypeKey: 'pitch-type.straight',
            course: { unit: '1/263' as const, x: '131', y: '132' },
            pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
            stance: null,
            battingSide: null,
            runnerObservation: p,
          }
    const before = structuredClone({ q, r, observations })
    const wire = await formatRunnerEventWire(
      q,
      r,
      observations,
      r.value.beforeParticipants,
    )
    expect(wire.payload.observations).toEqual(observations)
    expect(wire.payload.calculation.request).toEqual(q)
    expect(wire.payload.calculation.response).toEqual(r)
    expect(wire.stateDiff).toEqual(r.value.newHistoryEntry.difference)
    expect(
      await formatLineupPrefixWire(
        q,
        r,
        observations,
        r.value.beforeParticipants,
      ),
    ).toEqual(wire)
    expect({ q, r, observations }).toEqual(before)
    expect(await playHash(lineupWireHead(q, r))).toBe(q.nextCheckpoint.digest)
    expect(q.source.priorArtifactSha256).toBe(
      authored.cases[index]!.request.source.priorArtifactSha256,
    )
  })
it('不正自己echoは再封印で補修せず拒否する', async () => {
  const { request: q, response: r } = await metadataCase(0)
  const changed = {
    ...q,
    nextCheckpoint: { ...q.nextCheckpoint, digest: '0'.repeat(64) },
  }
  const observed = {
    kind: 'non-pitch-event' as const,
    runnerObservation: q.t1.runnerObservation,
  }
  await expect(
    formatRunnerEventWire(changed, r, observed, r.value.beforeParticipants),
  ).rejects.toThrow()
  await expect(
    formatLineupPrefixWire(changed, r, observed, r.value.beforeParticipants),
  ).rejects.toThrow()
  expect(changed.nextCheckpoint.digest).toBe('0'.repeat(64))
})
it('V7原観測の別値を数学要求へ合わせて書き換えない', async () => {
  const { request: q, response: r } = await metadataCase(0)
  const original = q.t1.runnerObservation
  const changed = { ...original, primaryResultId: 'batting-result.ball' }
  await expect(
    formatRunnerEventWire(
      q,
      r,
      { kind: 'non-pitch-event', runnerObservation: changed },
      r.value.beforeParticipants,
    ),
  ).rejects.toThrow()
  expect(changed.primaryResultId).toBe('batting-result.ball')
})
it('同じ要求の再構成は同じ本文/差分になり、新D5や新数学値を作らない', async () => {
  const { request: q, response: r } = await metadataCase(0)
  const observed = {
    kind: 'non-pitch-event' as const,
    runnerObservation: q.t1.runnerObservation,
  }
  const first = await formatRunnerEventWire(
    q,
    r,
    observed,
    r.value.beforeParticipants,
  )
  expect(
    await formatRunnerEventWire(q, r, observed, r.value.beforeParticipants),
  ).toEqual(first)
  expect(first.payload.calculation.request.playIdentity).toEqual(q.playIdentity)
})

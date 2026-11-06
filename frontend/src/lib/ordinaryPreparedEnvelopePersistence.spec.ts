import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  OrdinaryPreparedEnvelopePersistence,
  PreparedEnvelopeError,
  type PreparedEnvelope,
} from './ordinaryPreparedEnvelopePersistence'

const tenantId = '11111111-1111-4111-8111-111111111111'
const gameId = '22222222-2222-4222-8222-222222222222'
const d5 = '33333333-3333-4333-8333-333333333333'
const attemptId = '44444444-4444-4444-8444-444444444444'
const handles: OrdinaryPreparedEnvelopePersistence[] = []

function prepared(proof = 'opaque-proof'): PreparedEnvelope {
  const fields = {
    V1: d5,
    V3: 'opaque-D4',
    V4: gameId,
    V5: '1',
    V6: 1,
    V7: { formatVersion: 'play-prefix-play-v3' },
    V8: { changed: true },
  }
  return {
    schemaVersion: 1,
    tenantId,
    gameId,
    d4: 'opaque-D4',
    d1: 1,
    d5,
    attemptId,
    observation: {
      resultId: 'batting-result.ball',
      pitchTypeKey: 'tenant.pitch.straight',
      screenX: 131.5,
      screenY: 124,
      view: 'catcher',
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
    },
    vocabulary: { tenantId, pitchTypeKeys: ['tenant.pitch.straight'] },
    event: { fields },
    requestBody: {
      recording_right_proof: proof,
      events: [
        {
          game_id: gameId,
          d4: 'opaque-D4',
          d1: 1,
          d5,
          event_kind: '1',
          d2: 1,
          payload: fields.V7,
          state_diff: fields.V8,
        },
      ],
    },
  }
}

async function open(): Promise<OrdinaryPreparedEnvelopePersistence> {
  const handle = await OrdinaryPreparedEnvelopePersistence.open()
  handles.push(handle)
  return handle
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => {
  handles.splice(0).forEach((handle) => handle.close())
  vi.unstubAllGlobals()
})

it('同一D1の異なるV12を競合保存しても1件だけ成立し原文を保持する', async () => {
  const a = await open()
  const b = await open()
  const one = prepared('first-proof')
  const two = prepared('second-proof')
  const results = await Promise.allSettled([a.save(one), b.save(two)])
  expect(
    results.filter((result) => result.status === 'fulfilled'),
  ).toHaveLength(1)
  expect(results.filter((result) => result.status === 'rejected')).toHaveLength(
    1,
  )
  const winner = results.find((result) => result.status === 'fulfilled')
  expect(winner?.status).toBe('fulfilled')
  if (winner?.status !== 'fulfilled') throw new Error('勝者がありません')
  expect(await a.read(one)).toEqual(winner.value)
  expect(await b.read(one)).toEqual(winner.value)
})

it('getter/undefinedを持つ本文を保存せず、既行の破損も閉拒否する', async () => {
  const store = await open()
  const bad = prepared() as PreparedEnvelope & { hidden?: unknown }
  Object.defineProperty(bad, 'hidden', {
    enumerable: true,
    get: () => {
      throw new Error('getter must not run')
    },
  })
  await expect(store.save(bad)).rejects.toBeInstanceOf(PreparedEnvelopeError)
  expect(await store.read(prepared())).toBeNull()
  const missing = prepared()
  const event = missing.requestBody.events[0] as Record<string, unknown>
  event.payload = undefined
  await expect(store.save(missing)).rejects.toBeInstanceOf(
    PreparedEnvelopeError,
  )
  expect(await store.read(prepared())).toBeNull()
})

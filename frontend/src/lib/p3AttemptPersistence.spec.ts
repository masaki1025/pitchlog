import { webcrypto } from 'node:crypto'
import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { P3ChangeBody } from '../api/pastCorrectionProduct'
import fixture from '../api/fixtures/lineupPrefixGame.recorded.v3.json'
import {
  P3AttemptPersistence,
  P3AttemptPersistenceError,
} from './p3AttemptPersistence'

const game = fixture.value
const tenantId = game.prefix_ref.tenantId
const d5 = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const deviceId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const attemptId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const handles: P3AttemptPersistence[] = []

function body(): P3ChangeBody {
  return {
    recovery_generation: game.recovery_generation,
    recording_right_proof: 'opaque-proof',
    change: {
      d5,
      game_id: game.id,
      event_kind: 'play_change',
      target_reference: { game: game.id, d4: game.current_d4, d1: 1 },
      expected_version: 1,
      payload: {
        formatVersion: 'p3-lineup-pitch-change-v1',
        expectedPrefixRef: game.prefix_ref,
        targetEventId: game.page.items[0]!.play_row.source_event_id,
        targetPlayId: game.page.items[0]!.play_row.id,
        originalResultId: 'batting-result.ball',
        replacementResultId: 'batting-result.called-pitch',
        replacementObservations: {
          pitchTypeKey: 'pitch-type.straight',
          course: { unit: '1/263', x: '100', y: '150' },
          pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
          stance: null,
          battingSide: null,
        },
      },
    },
  } as P3ChangeBody
}

async function open() {
  const h = await P3AttemptPersistence.open()
  handles.push(h)
  return h
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('crypto', webcrypto)
})
afterEach(() => {
  for (const h of handles.splice(0)) h.close()
  vi.unstubAllGlobals()
})

it('送信前全原文と同attemptを再起動後にも復元する', async () => {
  const first = await open()
  const saved = await first.prepare({
    tenantId,
    gameId: game.id,
    deviceId,
    attemptId,
    body: body(),
  })
  first.close()
  const second = await open()
  expect(await second.read(tenantId, game.id)).toEqual(saved)
  expect(saved.requestJson).toContain('p3-lineup-pitch-change-v1')
  expect(saved.requestSha256).toMatch(/^[a-f0-9]{64}$/)
})

it('同試合の新D5/異本文を追加できず元要求を保持する', async () => {
  const store = await open()
  const original = await store.prepare({
    tenantId,
    gameId: game.id,
    deviceId,
    attemptId,
    body: body(),
  })
  const initial = body()
  const changed = {
    ...initial,
    change: {
      ...initial.change,
      d5: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    },
  }
  await expect(
    store.prepare({
      tenantId,
      gameId: game.id,
      deviceId,
      attemptId,
      body: changed,
    }),
  ).rejects.toBeInstanceOf(P3AttemptPersistenceError)
  expect(await store.read(tenantId, game.id)).toEqual(original)
})

it('保存原文の破損を旧成功や新要求に読み替えない', async () => {
  const store = await open()
  await store.prepare({
    tenantId,
    gameId: game.id,
    deviceId,
    attemptId,
    body: body(),
  })
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.open('pitchlog-p3-product-attempts', 1)
    request.onerror = () => reject(request.error)
    request.onsuccess = () => {
      const db = request.result
      const transaction = db.transaction('attempts', 'readwrite')
      const read = transaction.objectStore('attempts').get([tenantId, game.id])
      read.onsuccess = () => {
        transaction.objectStore('attempts').put({
          ...read.result,
          requestSha256: '0'.repeat(64),
        })
      }
      transaction.oncomplete = () => {
        db.close()
        resolve()
      }
      transaction.onerror = () => reject(transaction.error)
    }
  })
  await expect(store.read(tenantId, game.id)).rejects.toBeInstanceOf(
    P3AttemptPersistenceError,
  )
})

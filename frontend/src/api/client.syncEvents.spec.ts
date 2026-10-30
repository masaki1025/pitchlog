import 'fake-indexeddb/auto'

import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import { buildSyncEventKindSet } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'
import {
  postSyncEvents,
  SYNC_EVENT_SEND_FAILURE,
  type SyncEventSendRequest,
} from './client.syncEvents'
import syncEventsSource from './client.syncEvents.ts?raw'

const gameId = 'f1e2d3c4-b5a6-4789-9abc-def012345678'
const d4 = 'generation-a'
const d5 = '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'
const scope: DurableQueueScope = { game: gameId, d4 }
const eventKinds = buildSyncEventKindSet({ stateCorrectionAdopted: false })

let pinia: Pinia
let databaseSequence = 0
const openedQueues: DurableQueue[] = []

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  setVerifiedAuthForTest(useAuthStore(), { teamName: '試験チーム' })
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  disposePinia(pinia)
  queryClient.clear()
})

function respond(body: string, status = 200): void {
  vi.mocked(fetch).mockResolvedValue(
    new Response(body, {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

async function openIsolatedQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const queue = await openDurableQueue({
    databaseName: `uf8-sync-events-${databaseSequence}`,
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  return queue
}

/** D1 を除く完成形(モックの状態差分つき)。 */
function pitchEvent(overrides: Record<string, unknown> = {}): SyncEvent {
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: '1',
      V6: '0007',
      V7: { resultId: 'ball' },
      V8: { marker: 'mock-state-diff' },
      ...overrides,
    },
  }
}

function slot(overrides: Partial<DurableQueueSlot> = {}): DurableQueueSlot {
  return {
    game: gameId,
    d4,
    d1: 1,
    d5,
    version: {},
    event: pitchEvent(),
    state: '未送信',
    ...overrides,
  }
}

function request(
  overrides: Partial<SyncEventSendRequest> = {},
): SyncEventSendRequest {
  return {
    gameId,
    recordingRightProof: 'proof-token',
    slots: [slot()],
    eventKinds,
    ...overrides,
  }
}

function sentBody(): unknown {
  const call = vi.mocked(fetch).mock.calls[0]
  const init = call?.[1] as RequestInit | undefined
  return JSON.parse(String(init?.body))
}

describe('E-1 への送信', () => {
  it('1 プレイを 1 回の POST で E-1 へ送る', async () => {
    respond('{}')

    const result = await postSyncEvents(request())

    expect(result.sent).toBe(true)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe(
      `/api/games/${gameId}/sync/events`,
    )
    expect((vi.mocked(fetch).mock.calls[0]?.[1] as RequestInit).method).toBe(
      'POST',
    )
  })

  it('本文を recording_right_proof と events[] の wire のキーで作る', async () => {
    respond('{}')

    await postSyncEvents(request())

    expect(sentBody()).toEqual({
      recording_right_proof: 'proof-token',
      events: [
        {
          d5,
          d1: 1,
          d4,
          game_id: gameId,
          event_kind: '1',
          d2: '0007',
          payload: { resultId: 'ball' },
          state_diff: { marker: 'mock-state-diff' },
        },
      ],
    })
  })

  it('永続化したスロットの D1 と送信本文の d1 が一致する', async () => {
    const queue = await openIsolatedQueue()
    const persisted = await queue.append(
      queue.prepareAppend({ scope, d5, version: {}, event: pitchEvent() }),
    )
    respond('{}')

    const result = await postSyncEvents(request({ slots: [persisted] }))

    expect(result.sent).toBe(true)
    if (!result.sent) return
    expect(result.requestBody.events[0]?.d1).toBe(persisted.d1)
    expect(persisted.d1).toBe(1)
  })
})

describe('送らない要求', () => {
  it('送るスロットが無ければ送らない', async () => {
    const result = await postSyncEvents(request({ slots: [] }))

    expect(result).toEqual({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.EMPTY_REQUEST,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('1 要求に複数の (試合, D4) が混ざっていれば送らない', async () => {
    const other = slot({
      d1: 2,
      d4: 'generation-b',
      event: pitchEvent({ V3: 'generation-b' }),
    })

    const result = await postSyncEvents(request({ slots: [slot(), other] }))

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.MIXED_SCOPE,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('スロットの試合が path と食い違えば送らない（試合軸）', async () => {
    const result = await postSyncEvents(
      request({ slots: [slot({ game: 'other-game' })] }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.GAME_ID_MISMATCH,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('試合の違うスロットが混ざれば送らない（イベントの V4 が正しくても）', async () => {
    const foreign = slot({ d1: 2, game: 'other-game', event: pitchEvent() })

    const result = await postSyncEvents(request({ slots: [slot(), foreign] }))

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.GAME_ID_MISMATCH,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('記録権の証明を wire の層で検査しない（正本 S-2）', async () => {
    respond('{}')

    const result = await postSyncEvents(
      request({ recordingRightProof: undefined }),
    )

    // 有無・型・形は処理段階が判定する(VF1・VF4 → B4 → 退避済み)。
    // ここで止めると B4 が到達不能になり、スロットが永久に未送信で残る。
    expect(result.sent).toBe(true)
  })

  it('イベントの D5 がスロットの D5 と食い違えば送らない', async () => {
    const result = await postSyncEvents(
      request({ slots: [slot({ event: pitchEvent({ V1: 'other-d5' }) })] }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.D5_MISMATCH,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('スロットの値が undefined なら送らない（JSON で黙って消えるため）', async () => {
    const result = await postSyncEvents(
      request({ slots: [slot({ event: pitchEvent({ V6: undefined }) })] }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.UNDEFINED_SLOT_VALUE,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('スロットの値が null なら止めずに処理段階へ渡す（正本 S-2）', async () => {
    respond('{}')

    const result = await postSyncEvents(
      request({ slots: [slot({ event: pitchEvent({ V6: null }) })] }),
    )

    expect(result.sent).toBe(true)
    expect(sentBody()).toMatchObject({ events: [{ d2: null }] })
  })

  it.each([
    ['0', 0],
    ['小数', 1.5],
    ['安全な整数の上限超え', Number.MAX_SAFE_INTEGER + 1],
    ['負の数', -1],
  ])('D1 が L-2 の整数でない(%s)なら送らない', async (_label, value) => {
    const result = await postSyncEvents(
      request({ slots: [slot({ d1: value })] }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.INVALID_D1,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('要求の中で D1 が重複していれば送らない', async () => {
    const result = await postSyncEvents(request({ slots: [slot(), slot()] }))

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.DUPLICATE_D1,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('イベントの試合の識別が path と食い違えば送らない', async () => {
    const result = await postSyncEvents(
      request({
        slots: [slot({ event: pitchEvent({ V4: 'other-game' }) })],
      }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.GAME_ID_MISMATCH,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('イベントの D4 がスロットの D4 と食い違えば送らない', async () => {
    const result = await postSyncEvents(
      request({
        slots: [slot({ event: pitchEvent({ V3: 'generation-z' }) })],
      }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.D4_MISMATCH,
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })
})

describe('完成形が正本の検査を通ること', () => {
  it('状態差分を欠いた毎球入力は検査に落ちて送らない', async () => {
    const withoutStateDiff: SyncEvent = {
      fields: { ...pitchEvent().fields },
    }
    delete (withoutStateDiff.fields as Record<string, unknown>).V8

    const result = await postSyncEvents(
      request({ slots: [slot({ event: withoutStateDiff })] }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.INVALID_EVENT,
      violation: { violation: 'missing-slot', target: 'V8' },
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('P3 だけが持つスロットが混ざっていれば送らない', async () => {
    const result = await postSyncEvents(
      request({
        slots: [slot({ event: pitchEvent({ V11: 'expected-version' }) })],
      }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.INVALID_EVENT,
      violation: { violation: 'forbidden-slot', target: 'V11' },
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('受理する種別の集合に無い種別は送らない', async () => {
    const result = await postSyncEvents(
      request({
        slots: [slot({ event: pitchEvent({ V5: '7' }) })],
        eventKinds,
      }),
    )

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.INVALID_EVENT,
    })
  })
})

describe('送信の失敗でキューの状態を変えない', () => {
  it('通信に失敗しても例外を投げず、スロットは未送信のままである', async () => {
    const queue = await openIsolatedQueue()
    const persisted = await queue.append(
      queue.prepareAppend({ scope, d5, version: {}, event: pitchEvent() }),
    )
    vi.mocked(fetch).mockRejectedValue(new Error('切断'))

    const result = await postSyncEvents(request({ slots: [persisted] }))

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.NO_RESPONSE,
    })
    expect((await queue.readSlot(scope, persisted.d1))?.state).toBe('未送信')
    expect(await queue.countUnsentSlots()).toBe(1)
  })

  it('サーバーが拒否してもスロットは未送信のままである', async () => {
    const queue = await openIsolatedQueue()
    const persisted = await queue.append(
      queue.prepareAppend({ scope, d5, version: {}, event: pitchEvent() }),
    )
    respond('{"error":{"message":"だめ"}}', 409)

    const result = await postSyncEvents(request({ slots: [persisted] }))

    expect(result).toMatchObject({
      sent: false,
      reason: SYNC_EVENT_SEND_FAILURE.RESPONSE_NOT_INTERPRETED,
      status: 409,
    })
    expect((await queue.readSlot(scope, persisted.d1))?.state).toBe('未送信')
  })

  it('送信モジュールがキューの変更メソッドを参照しない', () => {
    for (const mutation of [
      'prepareAppend',
      'append(',
      'persistA5Transition',
      'replaceRevision',
      'replaceWithTombstone',
      'openDurableQueue',
    ]) {
      expect(syncEventsSource).not.toContain(mutation)
    }
  })
})

describe('同期POST専用の実資格輸送', () => {
  const credentials = {
    deviceId: '11111111-1111-4111-8111-111111111111',
    deviceCredential: 'fixture-device-credential',
    attempt: '22222222-2222-4222-8222-222222222222',
  }
  it('資格と固定attemptをヘッダへ渡し本文へ複製しない', async () => {
    respond('{}')
    const result = await postSyncEvents(
      request({ syncCredentials: credentials }),
    )
    expect(result.sent).toBe(true)
    const init = vi.mocked(fetch).mock.calls[0]![1]!
    expect(init.headers).toMatchObject({
      'X-Pitchlog-Device-Id': credentials.deviceId,
      'X-Pitchlog-Device-Credential': credentials.deviceCredential,
      'X-Pitchlog-Sync-Attempt': credentials.attempt,
    })
    expect(init.body).not.toContain(credentials.deviceCredential)
    expect(init.credentials).toBe('include')
  })
  it.each(['', 'bad\r\nheader', '非ASCII'])(
    '不正資格は送信しない: %s',
    async (deviceCredential) => {
      const result = await postSyncEvents(
        request({ syncCredentials: { ...credentials, deviceCredential } }),
      )
      expect(result.sent).toBe(false)
      expect(fetch).not.toHaveBeenCalled()
    },
  )
})

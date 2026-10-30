import 'fake-indexeddb/auto'

import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { createAckAdapterInjections } from '../lib/sync/ackAdapter'
import { CANON_ACK_STATE_RESULT } from '../lib/sync/canonOracle'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
} from '../lib/sync/durableQueue'
import { buildSyncEventKindSet } from '../lib/sync/eventKinds'
import { queueStateId } from '../lib/sync/queueState'
import { B3_REJECTION_KIND } from '../lib/sync/rejectionReason'
import type {
  ExclusiveLockManager,
  SingleWriterInjections,
} from '../lib/sync/singleWriter'
import type { SyncEvent } from '../lib/sync/syncEvent'
import type { AckResponse } from './GameScreenAckApplication'
import {
  commitPitchEvent,
  PITCH_COMMIT_SCOPE_MISMATCH,
  type PitchCommitDependencies,
  type PitchCommitInput,
} from './GameScreenPitchCommit'

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

async function openIsolatedQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const queue = await openDurableQueue({
    databaseName: `uf8-pitch-commit-${databaseSequence}`,
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  return queue
}

/** モックの状態差分つきの毎球入力イベント。 */
function pitchEvent(): SyncEvent {
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: '1',
      V6: '0007',
      V7: { resultId: 'ball' },
      V8: { marker: 'mock-state-diff' },
    },
  }
}

/** 鍵の取得と解放を記録する管理機構。 */
function recordingLockManager(log: string[]): ExclusiveLockManager {
  return {
    request: async (name, callback) => {
      log.push(`acquire:${name}`)
      try {
        return await callback({ granted: true })
      } finally {
        log.push(`release:${name}`)
      }
    },
  }
}

function singleWriterInjections(
  overrides: Partial<SingleWriterInjections> = {},
): SingleWriterInjections {
  return {
    resolvePreconditions: () => ({
      topLevelHttps: true,
      sameBrowserProfile: true,
      sameBrowsingMode: true,
      sameStorageBucket: true,
      siteStorageAvailable: true,
      lockdownModeNotApplied: true,
    }),
    revalidateSingleWriter: () => true,
    lockManager: recordingLockManager([]),
    ...overrides,
  }
}

function input(overrides: Partial<PitchCommitInput> = {}): PitchCommitInput {
  return {
    gameIdentifier: gameId,
    scope,
    d5,
    version: { marker: 'v1' },
    event: pitchEvent(),
    recordingRightProof: 'proof-token',
    eventKinds,
    ...overrides,
  }
}

function ackFromResponse(a5Result: string, boundaryResult = 'B1') {
  return (response: unknown): AckResponse | undefined => {
    void response
    return {
      envelope: {
        advancedD3: 0,
        eventResults: [{ d4, d1: 1, d5, a5Result }],
      },
      boundaryResult,
    }
  }
}

function dependencies(
  queue: DurableQueue,
  overrides: Partial<PitchCommitDependencies> = {},
): PitchCommitDependencies {
  return {
    queue,
    singleWriterInjections: singleWriterInjections(),
    readAck: () => undefined,
    ...overrides,
  }
}

function respond(body: string, status = 200): void {
  vi.mocked(fetch).mockResolvedValue(
    new Response(body, {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

describe('確定の経路を 1 つの排他で包む', () => {
  it('排他を 1 回だけ取り、その中で追記から ACK の適用まで行う', async () => {
    const queue = await openIsolatedQueue()
    const lockLog: string[] = []
    respond('{}')

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({
          lockManager: recordingLockManager(lockLog),
        }),
        readAck: ackFromResponse(CANON_ACK_STATE_RESULT.ACCEPTED),
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.acceptance.outcome).toBe('accepted')
    expect(result.send?.sent).toBe(true)
    expect(result.ackApplication?.outcome).toBe('applied')

    // 排他は 1 回だけ。旧実装は再送にしか鍵を掛けていなかった。
    expect(lockLog).toEqual([
      `acquire:pitchlog:game:${gameId}`,
      `release:pitchlog:game:${gameId}`,
    ])
  })

  it('送信と ACK の適用が排他の解放より前に起きる', async () => {
    const queue = await openIsolatedQueue()
    const order: string[] = []
    respond('{}')
    vi.mocked(fetch).mockImplementation(async () => {
      order.push('send')
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })

    await commitPitchEvent(
      input(),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({
          lockManager: {
            request: async (_name, callback) => {
              order.push('acquire')
              try {
                return await callback({ granted: true })
              } finally {
                order.push('release')
              }
            },
          },
        }),
        readAck: (response) => {
          order.push('read-ack')
          void response
          return undefined
        },
      }),
    )

    expect(order).toEqual(['acquire', 'send', 'read-ack', 'release'])
  })

  it('受理の ACK でスロットが同期済みになる', async () => {
    const queue = await openIsolatedQueue()
    respond('{}')

    await commitPitchEvent(
      input(),
      dependencies(queue, {
        readAck: ackFromResponse(CANON_ACK_STATE_RESULT.ACCEPTED),
      }),
    )

    expect((await queue.readSlot(scope, 1))?.state).toBe(
      queueStateId('同期済み'),
    )
  })

  it('応答が遅延している間も追記済みのスロットを保持し、ACKまで排他を解放しない', async () => {
    const queue = await openIsolatedQueue()
    const lockLog: string[] = []
    let resolveResponse!: (value: Response) => void
    let markSending!: () => void
    const response = new Promise<Response>((resolve) => {
      resolveResponse = resolve
    })
    const sending = new Promise<void>((resolve) => {
      markSending = resolve
    })
    vi.mocked(fetch).mockImplementation(() => {
      markSending()
      return response
    })

    const pending = commitPitchEvent(
      input(),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({
          lockManager: recordingLockManager(lockLog),
        }),
        readAck: ackFromResponse(CANON_ACK_STATE_RESULT.ACCEPTED),
      }),
    )
    await sending

    try {
      expect((await queue.readSlot(scope, 1))?.state).toBe(
        queueStateId('未送信'),
      )
      expect(await queue.readNextD1(scope)).toBe(2)
      expect(lockLog).toEqual([`acquire:pitchlog:game:${gameId}`])
    } finally {
      resolveResponse(
        new Response('{}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }

    const result = await pending
    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.latestSlot?.state).toBe(queueStateId('同期済み'))
    expect(lockLog).toEqual([
      `acquire:pitchlog:game:${gameId}`,
      `release:pitchlog:game:${gameId}`,
    ])
  })

  it('B3 を含む ACK の拒否でスロットが要操作になる', async () => {
    const queue = await openIsolatedQueue()
    respond('{}')

    await commitPitchEvent(
      input(),
      dependencies(queue, {
        readAck: () => ({
          envelope: {
            advancedD3: 0,
            eventResults: [
              { d4, d1: 1, d5, a5Result: CANON_ACK_STATE_RESULT.REJECTED },
            ],
          },
          boundaryResult: 'B3',
          b3Rejection: { kind: B3_REJECTION_KIND.O4, reason: 'opaque-reason' },
        }),
      }),
    )

    expect((await queue.readSlot(scope, 1))?.state).toBe(queueStateId('要操作'))
  })
})

describe('排他が取れなければ追記も送信もしない', () => {
  it('鍵の管理機構が無ければ何もしない', async () => {
    const queue = await openIsolatedQueue()

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({ lockManager: null }),
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.acceptance).toMatchObject({
      outcome: 'not-accepted',
      reason: 'single-writer-not-started',
    })
    expect(result.send).toBeUndefined()
    expect(await queue.countSlots()).toBe(0)
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('再確認が通らなければ何もしない', async () => {
    const queue = await openIsolatedQueue()

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({
          revalidateSingleWriter: () => false,
        }),
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.send).toBeUndefined()
    expect(await queue.countSlots()).toBe(0)
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })
})

describe('追記が成立しなければ送信しない', () => {
  it('追記に失敗したら送らない', async () => {
    const queue = await openIsolatedQueue()
    const failingAppend = {
      prepareAppend: (value: Parameters<DurableQueue['prepareAppend']>[0]) =>
        queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      readSlot: (target: DurableQueueScope, d1: number) =>
        queue.readSlot(target, d1),
      readNextD1: (target: DurableQueueScope) => queue.readNextD1(target),
      prepareA5Transition: (target: DurableQueueScope, d1: number) =>
        queue.prepareA5Transition(target, d1),
      persistA5Transition: (
        preparation: Parameters<DurableQueue['persistA5Transition']>[0],
      ) => queue.persistA5Transition(preparation),
    }

    const result = await commitPitchEvent(
      input(),
      dependencies(failingAppend as unknown as DurableQueue),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.acceptance.outcome).toBe('not-accepted')
    expect(result.send).toBeUndefined()
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })
})

describe('送信できなければ ACK を適用しない', () => {
  it('通信に失敗したらスロットは未送信のまま', async () => {
    const queue = await openIsolatedQueue()
    vi.mocked(fetch).mockRejectedValue(new Error('切断'))

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        readAck: ackFromResponse(CANON_ACK_STATE_RESULT.ACCEPTED),
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.acceptance.outcome).toBe('accepted')
    expect(result.send?.sent).toBe(false)
    expect(result.ackApplication).toBeUndefined()
    expect((await queue.readSlot(scope, 1))?.state).toBe(queueStateId('未送信'))
  })

  it('ACK を取り出せなければスロットは未送信のまま', async () => {
    const queue = await openIsolatedQueue()
    respond('{}')

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        readAck: () => {
          throw new Error('応答を読めません')
        },
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.ackApplication).toMatchObject({
      outcome: 'not-applied',
      reason: 'no-ack-received',
    })
    expect((await queue.readSlot(scope, 1))?.state).toBe(queueStateId('未送信'))
  })
})

describe('前提が合わなければ排他も取らない', () => {
  it('排他の単位とキューの試合が食い違えば止める', async () => {
    const queue = await openIsolatedQueue()
    const lockLog: string[] = []

    const result = await commitPitchEvent(
      input({ scope: { game: 'other-game', d4 } }),
      dependencies(queue, {
        singleWriterInjections: singleWriterInjections({
          lockManager: recordingLockManager(lockLog),
        }),
      }),
    )

    expect(result).toEqual({
      outcome: 'not-attempted',
      reason: PITCH_COMMIT_SCOPE_MISMATCH,
    })
    expect(lockLog).toEqual([])
    expect(await queue.countSlots()).toBe(0)
  })
})

describe('最新のスロットと、既に遷移したスロットの扱い', () => {
  it('ACK を適用したら、その後の状態を最新として返す', async () => {
    const queue = await openIsolatedQueue()
    respond('{}')

    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        readAck: ackFromResponse(CANON_ACK_STATE_RESULT.ACCEPTED),
      }),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    // 追記直後は未送信、適用後は同期済み。最新は後者でなければならない。
    expect(result.acceptance.outcome).toBe('accepted')
    if (result.acceptance.outcome !== 'accepted') return
    expect(result.acceptance.slot.state).toBe(queueStateId('未送信'))
    expect(result.latestSlot?.state).toBe(queueStateId('同期済み'))
  })

  it('ACK が無ければ、追記直後のスロットが最新である', async () => {
    const queue = await openIsolatedQueue()
    vi.mocked(fetch).mockRejectedValue(new Error('切断'))

    const result = await commitPitchEvent(input(), dependencies(queue))

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.latestSlot?.state).toBe(queueStateId('未送信'))
  })

  it('照合で拾ったスロットが既に遷移済みなら送り直さない', async () => {
    const queue = await openIsolatedQueue()
    // 先に同じ D1 へ積んで同期済みにしておく。
    const persisted = await queue.append(
      queue.prepareAppend({ scope, d5, version: {}, event: pitchEvent() }),
    )
    const preparation = await queue.prepareA5Transition(
      scope,
      persisted.d1,
      createAckAdapterInjections({
        d1: {
          envelope: {
            advancedD3: 0,
            eventResults: [
              {
                d4,
                d1: persisted.d1,
                d5,
                a5Result: CANON_ACK_STATE_RESULT.ACCEPTED,
              },
            ],
          },
          boundaryResult: 'B1',
        },
      }),
    )
    if (!preparation) throw new Error('preparation がありません')
    await queue.persistA5Transition(preparation)
    expect((await queue.readSlot(scope, persisted.d1))?.state).toBe(
      queueStateId('同期済み'),
    )

    // 追記は失敗させ、照合でその同期済みスロットを拾わせる。
    const reconciling = {
      prepareAppend: (value: Parameters<DurableQueue['prepareAppend']>[0]) =>
        queue.prepareAppend(value),
      append: () => Promise.reject(new Error('追記できません')),
      countUnsentSlots: () => queue.countUnsentSlots(),
      readSlot: () => queue.readSlot(scope, persisted.d1),
      readNextD1: () => Promise.resolve(persisted.d1),
      prepareA5Transition: (target: typeof scope, d1: number) =>
        queue.prepareA5Transition(target, d1),
      persistA5Transition: (
        value: Parameters<DurableQueue['persistA5Transition']>[0],
      ) => queue.persistA5Transition(value),
    }

    const result = await commitPitchEvent(
      input(),
      dependencies(reconciling as unknown as DurableQueue),
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.send).toBeUndefined()
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })
})

describe('HTTP前の耐久送信準備', () => {
  const credentials = {
    deviceId: '11111111-1111-4111-8111-111111111111',
    deviceCredential: 'fixture-device-credential',
    attempt: '22222222-2222-4222-8222-222222222222',
  }
  it('追記後の準備を同じ排他内で待ち、完了までHTTPを送らない', async () => {
    const queue = await openIsolatedQueue()
    const lockLog: string[] = []
    let complete!: (value: typeof credentials) => void
    let preparing!: () => void
    const started = new Promise<void>((resolve) => {
      preparing = resolve
    })
    const barrier = new Promise<typeof credentials>((resolve) => {
      complete = resolve
    })
    const prepareSend: NonNullable<
      PitchCommitDependencies['prepareSend']
    > = async (request) => {
      expect(request.gameId).toBe(gameId)
      expect(request.slots).toHaveLength(1)
      expect(request.slots[0]!.d1).toBe(1)
      expect((await queue.readSlot(scope, 1))?.state).toBe(
        queueStateId('未送信'),
      )
      preparing()
      return barrier
    }
    respond('{}')
    const pending = commitPitchEvent(
      input(),
      dependencies(queue, {
        prepareSend,
        singleWriterInjections: singleWriterInjections({
          lockManager: recordingLockManager(lockLog),
        }),
      }),
    )
    await started
    expect(fetch).not.toHaveBeenCalled()
    expect(lockLog).toEqual([`acquire:pitchlog:game:${gameId}`])
    complete(credentials)
    const result = await pending
    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.send?.sent).toBe(true)
    expect(result.sendPreparation).toBeUndefined()
    expect(vi.mocked(fetch).mock.calls[0]![1]!.headers).toMatchObject({
      'X-Pitchlog-Sync-Attempt': credentials.attempt,
      'X-Pitchlog-Device-Id': credentials.deviceId,
      'X-Pitchlog-Device-Credential': credentials.deviceCredential,
    })
    expect(lockLog).toEqual([
      `acquire:pitchlog:game:${gameId}`,
      `release:pitchlog:game:${gameId}`,
    ])
  })
  it('準備失敗はHTTP未送信として明示し、追記済みslotを保持する', async () => {
    const queue = await openIsolatedQueue()
    const result = await commitPitchEvent(
      input(),
      dependencies(queue, {
        prepareSend: async () => {
          throw new Error('private-material-marker')
        },
      }),
    )
    expect(fetch).not.toHaveBeenCalled()
    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.sendPreparation).toEqual({ outcome: 'failed' })
    expect(result.send).toBeUndefined()
    expect(result.ackApplication).toBeUndefined()
    expect(result.latestSlot?.d1).toBe(1)
    expect(result.latestSlot?.state).toBe(queueStateId('未送信'))
    expect((await queue.readSlot(scope, 1))?.state).toBe(queueStateId('未送信'))
    expect(await queue.readNextD1(scope)).toBe(2)
    expect(JSON.stringify(result)).not.toContain('private-material-marker')
  })
  it('排他が得られなければ送信準備も行わない', async () => {
    const queue = await openIsolatedQueue()
    const prepareSend = vi.fn(async () => credentials)
    await commitPitchEvent(
      input(),
      dependencies(queue, {
        prepareSend,
        singleWriterInjections: singleWriterInjections({
          lockManager: {
            request: async (_name, callback) => callback(null),
          },
        }),
      }),
    )
    expect(prepareSend).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })
})

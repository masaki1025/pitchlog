import 'fake-indexeddb/auto'

import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
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

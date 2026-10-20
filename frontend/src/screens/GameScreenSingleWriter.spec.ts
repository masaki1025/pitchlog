import 'fake-indexeddb/auto'

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
} from '../lib/sync/durableQueue'
import { buildSyncEventKindSet } from '../lib/sync/eventKinds'
import { parseFailureScenarioContract } from '../lib/sync/failureScenarioContract'
import {
  SINGLE_WRITER_PRECONDITION_IDS,
  type SingleWriterPreconditions,
} from '../lib/sync/singleWriter'
import type { SyncEvent } from '../lib/sync/syncEvent'
import { commitPitchEvent } from './GameScreenPitchCommit'
import {
  createNonBlockingLockManager,
  withNonBlockingSingleWriter,
} from './GameScreenSingleWriter'

const gameId = 'f1e2d3c4-b5a6-4789-9abc-def012345678'
const d4 = 'generation-a'
const d5 = '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'
const scope: DurableQueueScope = { game: gameId, d4 }

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
    databaseName: `uf8-single-writer-${databaseSequence}`,
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  return queue
}

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

function preconditions(): SingleWriterPreconditions {
  return Object.fromEntries(
    SINGLE_WRITER_PRECONDITION_IDS.map((id) => [id, true]),
  ) as SingleWriterPreconditions
}

/** 鍵が他で保持されている Web Locks を模す。 */
function heldLocks() {
  return {
    request: (
      _name: string,
      options: { ifAvailable?: true } | ((lock: unknown) => unknown),
      callback?: (lock: unknown) => unknown,
    ) => {
      const run = typeof options === 'function' ? options : callback
      if (!run) {
        throw new Error('コールバックがありません')
      }
      // ifAvailable を渡されたら、取れないので null を渡して即座に戻る。
      if (typeof options !== 'function' && options.ifAvailable === true) {
        return Promise.resolve(run(null))
      }
      // 既定(ブロッキング)なら、解放を待ってから実行する相手を模す。
      return new Promise((settle) => {
        setTimeout(() => settle(run({ granted: true })), 0)
      })
    },
  }
}

describe('待たない管理機構が既定であること', () => {
  it('lockManager を渡さなければ、待たない管理機構が入る', () => {
    const injections = withNonBlockingSingleWriter({
      resolvePreconditions: preconditions,
    })

    expect(injections.lockManager).toBeDefined()
    expect(injections.resolvePreconditions).toBeDefined()
  })

  it('呼出元が渡した管理機構は上書きしない', () => {
    const lockManager = createNonBlockingLockManager(() =>
      Promise.resolve(null),
    )
    const injections = withNonBlockingSingleWriter({ lockManager })

    expect(injections.lockManager).toBe(lockManager)
  })
})

describe('待機中の非所有タブの確定(E5 の契約資産)', () => {
  const contract = parseFailureScenarioContract(
    'waiting-input-not-accepted_v2.json',
    readFileSync(
      resolve(
        cwd(),
        '../tests/fixtures/sync-protocol-failures/waiting-input-not-accepted_v2.json',
      ),
      'utf8',
    ),
  )
  const observation = contract.cases[0]?.observations[0]

  it('資産は「キューへ追記せず D1 を消費しない」を求めている', () => {
    expect(observation?.fields.queue).toMatchObject({ appendCount: 0 })
    expect(observation?.fields.d1).toMatchObject({ consumed: false })
    expect(observation?.fields.acceptanceDisplay).toMatchObject({
      shownAsAccepted: false,
      noticeId: 'Q2-b',
    })
  })

  it('他のタブが鍵を保持していたら、追記も採番も送信もしない', async () => {
    // 呼出元の注入ではなく、ブラウザ既定のWeb Locksを差し替える。
    // withNonBlockingSingleWriterを確定経路から外すと追記され、この試験が落ちる。
    vi.stubGlobal('navigator', { locks: heldLocks() })
    const queue = await openIsolatedQueue()
    const nextD1Before = await queue.readNextD1(scope)

    const result = await commitPitchEvent(
      {
        gameIdentifier: gameId,
        scope,
        d5,
        version: {},
        event: pitchEvent(),
        recordingRightProof: 'proof-token',
        eventKinds: buildSyncEventKindSet({ stateCorrectionAdopted: false }),
      },
      {
        queue,
        // lockManager は渡さない。既定が待たない管理機構であることを確かめる。
        singleWriterInjections: {
          resolvePreconditions: preconditions,
          revalidateSingleWriter: () => true,
        },
        readAck: () => undefined,
      },
    )

    expect(result.outcome).toBe('attempted')
    if (result.outcome !== 'attempted') return
    expect(result.acceptance.outcome).toBe('not-accepted')
    expect(await queue.countSlots()).toBe(0)
    expect(await queue.readNextD1(scope)).toBe(nextD1Before)
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
    // 記録できないことと導線を示す記述子が載る(要件書 :333 の E3)。
    expect(result.nonOwner).toMatchObject({
      accepted: false,
      notice: { noticeId: 'Q2-b' },
    })
  })
})

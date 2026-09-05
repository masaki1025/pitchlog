import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import clientDisciplineSource from './clientDiscipline.ts?raw'
import {
  appendUnderQueueDiscipline,
  CLIENT_CLEANUP_TRIGGER,
  CLIENT_DISCIPLINE_RULES,
  coordinateAuthenticationSync,
  DEFAULT_UNSENT_WARNING_THRESHOLD,
  planQueueCleanup,
  type ClientCleanupInjections,
  type QueueCleanupCandidate,
} from './clientDiscipline'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
  type DurableQueueSlot,
} from './durableQueue'
import { queueStateId, type QueueStateId } from './queueState'
import { RG1_STATE, type QueueSlot } from './queueTransition'

let databaseSequence = 0
const openedQueues: DurableQueue[] = []
const databaseNames: string[] = []

function nextDatabaseName(): string {
  databaseSequence += 1
  const name = `client-discipline-${databaseSequence}`
  databaseNames.push(name)
  return name
}

async function openTestQueue(): Promise<DurableQueue> {
  const queue = await openDurableQueue({
    databaseName: nextDatabaseName(),
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  return queue
}

function appendInput(
  scope: DurableQueueScope,
  marker: number,
): DurableQueueAppend {
  return {
    scope,
    d5: { marker },
    version: { marker },
    event: { fields: {} },
  }
}

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('テスト DB を削除できません'))
  })
}

function openExistingDatabase(name: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(transaction.error)
    transaction.onerror = () => {
      // abort が最終結果を通知するため、ここでは完了を確定しない。
    }
  })
}

async function overwriteQueueSlot(
  databaseName: string,
  slot: DurableQueueSlot,
): Promise<void> {
  const database = await openExistingDatabase(databaseName)
  const transaction = database.transaction('queue', 'readwrite')
  const completion = transactionDone(transaction)
  transaction.objectStore('queue').put(slot)
  await completion
  database.close()
}

afterEach(async () => {
  vi.restoreAllMocks()
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  for (const name of databaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

function queueSlot(state: QueueStateId): QueueSlot {
  return {
    state,
    source: 'd1-event',
    key: { d4: {}, d1: {}, d5: {} },
    content: {},
  }
}

function cleanupCandidate(
  state: QueueStateId,
  confirmed24HoursElapsed: boolean,
): QueueCleanupCandidate {
  return {
    slot: queueSlot(state),
    confirmed24HoursElapsed,
  }
}

describe('clientDiscipline', () => {
  it('実装するクライアント規律を Q3・Q7 のみに閉じる', () => {
    expect(CLIENT_DISCIPLINE_RULES.map((rule) => rule.id)).toEqual(['Q3', 'Q7'])
  })

  it('Q3: 未送信 351 件でも追記をブロックせず、閾値到達の事実だけを返す', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }

    for (
      let index = 0;
      index < DEFAULT_UNSENT_WARNING_THRESHOLD - 1;
      index += 1
    ) {
      await queue.append(queue.prepareAppend(appendInput(scope, index)))
    }
    const thresholdResult = await appendUnderQueueDiscipline(
      queue,
      appendInput(scope, DEFAULT_UNSENT_WARNING_THRESHOLD - 1),
    )
    const aboveThresholdResult = await appendUnderQueueDiscipline(
      queue,
      appendInput(scope, DEFAULT_UNSENT_WARNING_THRESHOLD),
    )

    expect(thresholdResult.unsentCount).toBe(DEFAULT_UNSENT_WARNING_THRESHOLD)
    expect(thresholdResult.warningThresholdReached).toBe(true)
    expect(thresholdResult.recordingBlocked).toBe(false)
    expect(aboveThresholdResult.unsentCount).toBe(
      DEFAULT_UNSENT_WARNING_THRESHOLD + 1,
    )
    expect(aboveThresholdResult.warningThresholdReached).toBe(true)
    expect(aboveThresholdResult.recordingBlocked).toBe(false)
    expect(aboveThresholdResult.slot.d1).toBe(
      DEFAULT_UNSENT_WARNING_THRESHOLD + 1,
    )
    expect(Reflect.ownKeys(aboveThresholdResult).sort()).toEqual(
      [
        'recordingBlocked',
        'slot',
        'unsentCount',
        'warningThresholdReached',
      ].sort(),
    )
  })

  it('Q3: 未送信以外の状態を永続化しても未送信件数に含めない', async () => {
    const queue = await openTestQueue()
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const scope = { game: 'game-a', d4: 'generation-a' }
    const nonUnsentStates = [
      queueStateId('要操作'),
      queueStateId('同期済み'),
      queueStateId('退避済み'),
    ] as const

    for (const [index, state] of nonUnsentStates.entries()) {
      const slot = await queue.append(
        queue.prepareAppend(appendInput(scope, index)),
      )
      await overwriteQueueSlot(databaseName, { ...slot, state })
    }
    expect(await queue.countUnsentSlots()).toBe(0)

    const result = await appendUnderQueueDiscipline(
      queue,
      appendInput(scope, nonUnsentStates.length),
      2,
    )

    expect(await queue.countSlots()).toBe(nonUnsentStates.length + 1)
    expect(result.unsentCount).toBe(1)
    expect(result.warningThresholdReached).toBe(false)
  })

  it('Q7: 認証失効中もキューと次の D1 を保ち、再ログイン後に同期を再開する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }
    await queue.append(queue.prepareAppend(appendInput(scope, 0)))
    await queue.append(queue.prepareAppend(appendInput(scope, 1)))
    const countBefore = await queue.countSlots()
    const nextD1Before = await queue.readNextD1(scope)
    const resumeSynchronization = vi.fn(async () => undefined)

    const expiredResult = await coordinateAuthenticationSync({
      resolveAuthenticationExpired: () => true,
      resumeSynchronization,
    })

    expect(expiredResult).toEqual({
      authenticationExpired: true,
      synchronizationResumed: false,
    })
    expect(resumeSynchronization).not.toHaveBeenCalled()
    expect(await queue.countSlots()).toBe(countBefore)
    expect(await queue.readNextD1(scope)).toBe(nextD1Before)

    const reloggedInResult = await coordinateAuthenticationSync({
      resolveAuthenticationExpired: () => false,
      resumeSynchronization,
    })
    expect(reloggedInResult).toEqual({
      authenticationExpired: false,
      synchronizationResumed: true,
    })
    expect(resumeSynchronization).toHaveBeenCalledTimes(1)
  })

  it('24 時間経過かつ RG1 中でないと確認済みの同期済みだけを破棄対象にする', async () => {
    const expiredSynced = cleanupCandidate(queueStateId('同期済み'), true)
    const freshSynced = cleanupCandidate(queueStateId('同期済み'), false)
    const result = await planQueueCleanup(
      CLIENT_CLEANUP_TRIGGER.EXPLICIT_REQUEST,
      {
        resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED,
        selectCleanupCandidates: () => [expiredSynced, freshSynced],
      },
    )

    expect(result.selectionStarted).toBe(true)
    expect(result.discardCandidates).toEqual([expiredSynced])
  })

  const deferredRg1Cases = [
    ['RG1 中', { resolveRg1State: () => RG1_STATE.ACTIVE }],
    ['確認不能', { resolveRg1State: () => RG1_STATE.UNKNOWN }],
    ['未注入', {}],
  ] as const satisfies readonly (readonly [string, ClientCleanupInjections])[]

  it.each(deferredRg1Cases)(
    '%sでは破棄対象を選別しない',
    async (_name, injections) => {
      const selectCleanupCandidates = vi.fn(() => [
        cleanupCandidate(queueStateId('同期済み'), true),
      ])
      const result = await planQueueCleanup(
        CLIENT_CLEANUP_TRIGGER.DEVICE_STARTUP,
        {
          ...injections,
          selectCleanupCandidates,
        },
      )

      expect(result.selectionStarted).toBe(false)
      expect(result.discardCandidates).toEqual([])
      expect(selectCleanupCandidates).not.toHaveBeenCalled()
    },
  )

  it('退避済みは 24 時間を流用せず破棄対象にしない', async () => {
    const evacuated = cleanupCandidate(queueStateId('退避済み'), true)
    const result = await planQueueCleanup(
      CLIENT_CLEANUP_TRIGGER.EXPLICIT_REQUEST,
      {
        resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED,
        selectCleanupCandidates: () => [evacuated],
      },
    )

    expect(result.selectionStarted).toBe(true)
    expect(result.discardCandidates).toEqual([])
  })

  it.each(Object.values(CLIENT_CLEANUP_TRIGGER))(
    '%sの経路だけで清掃候補を選別する',
    async (trigger) => {
      const candidate = cleanupCandidate(queueStateId('同期済み'), true)
      const result = await planQueueCleanup(trigger, {
        resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED,
        selectCleanupCandidates: () => [candidate],
      })

      expect(Object.values(CLIENT_CLEANUP_TRIGGER)).toHaveLength(2)
      expect(result.discardCandidates).toEqual([candidate])
    },
  )

  it('端末起動時は RG1 確認を期限清掃より先に行う', async () => {
    const invocationOrder: string[] = []

    await planQueueCleanup(CLIENT_CLEANUP_TRIGGER.DEVICE_STARTUP, {
      resolveRg1State: () => {
        invocationOrder.push('rg1')
        return RG1_STATE.INACTIVE_CONFIRMED
      },
      selectCleanupCandidates: () => {
        invocationOrder.push('cleanup')
        return []
      },
    })

    expect(invocationOrder).toEqual(['rg1', 'cleanup'])
  })

  it('タイマーによる自動清掃を登録しない', () => {
    expect(clientDisciplineSource).not.toContain('setInterval')
    expect(clientDisciplineSource).not.toContain('setTimeout')
    expect(clientDisciplineSource).not.toContain('requestIdleCallback')
  })
})

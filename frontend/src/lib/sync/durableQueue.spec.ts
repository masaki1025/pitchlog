import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import durableQueueSource from './durableQueue.ts?raw'
import {
  DurableQueueUnavailableError,
  openDurableQueue,
  type D1Allocator,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
  type DurableQueueSlot,
} from './durableQueue'
import { REQUEST_ONLY_IDS, SYNC_EVENT_PATH } from './eventFieldRules'
import {
  prepareTombstoneReplacement,
  TOMBSTONE_ONLINE_STATE,
  type TombstoneBoundaryRequest,
  type TombstoneGenerationInjections,
} from './k5Tombstone'
import { actionRequiredLabelId, queueStateId } from './queueState'

let databaseSequence = 0
const openedQueues: DurableQueue[] = []
const databaseNames: string[] = []
const REQUEST_ONLY_ID = REQUEST_ONLY_IDS[0]
if (!REQUEST_ONLY_ID) {
  throw new Error('要求レベル ID がありません')
}

function nextDatabaseName(): string {
  databaseSequence += 1
  const name = `durable-queue-${databaseSequence}`
  databaseNames.push(name)
  return name
}

async function openTestQueue(
  overrides: Partial<Parameters<typeof openDurableQueue>[0]> = {},
): Promise<DurableQueue> {
  const queue = await openDurableQueue({
    databaseName: nextDatabaseName(),
    requestStoragePersistence: async () => false,
    ...overrides,
  })
  openedQueues.push(queue)
  return queue
}

function appendInput(
  scope: DurableQueueScope,
  overrides: Partial<DurableQueueAppend> = {},
): DurableQueueAppend {
  return {
    scope,
    d5: {},
    version: {},
    event: { fields: {} },
    ...overrides,
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

function tombstoneBoundaryRequest(
  slot: DurableQueueSlot,
  overrides: Partial<TombstoneBoundaryRequest> = {},
): TombstoneBoundaryRequest {
  return {
    path: SYNC_EVENT_PATH.P1,
    requestValues: { [REQUEST_ONLY_ID]: {} },
    recoveryGenerationAtCreation: {},
    game: slot.game,
    d4: slot.d4,
    d1: slot.d1,
    ...overrides,
  }
}

function successfulTombstoneInjections(
  newD5: unknown,
  overrides: Partial<TombstoneGenerationInjections> = {},
): TombstoneGenerationInjections {
  return {
    resolveOnlineState: () => TOMBSTONE_ONLINE_STATE.ONLINE,
    v12Binding: () => true,
    generateD5: () => newD5,
    ...overrides,
  }
}

afterEach(async () => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  for (const name of databaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

describe('durableQueue', () => {
  it('(試合, D4) ごとに D1 を 1 から連続して採番する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }

    const first = await queue.append(appendInput(scope))
    const second = await queue.append(appendInput(scope))
    const third = await queue.append(appendInput(scope))

    expect([first.d1, second.d1, third.d1]).toEqual([1, 2, 3])
    expect(await queue.readNextD1(scope)).toBe(4)
  })

  it('別の (試合, D4) の D1 カウンタを独立させる', async () => {
    const queue = await openTestQueue()
    const firstScope = { game: 'game-a', d4: 'generation-a' }
    const secondScope = { game: 'game-a', d4: 'generation-b' }
    const thirdScope = { game: 'game-b', d4: 'generation-a' }

    await queue.append(appendInput(firstScope))
    await queue.append(appendInput(firstScope))
    const secondFirst = await queue.append(appendInput(secondScope))
    const thirdFirst = await queue.append(appendInput(thirdScope))

    expect(await queue.readNextD1(firstScope)).toBe(3)
    expect(secondFirst.d1).toBe(1)
    expect(thirdFirst.d1).toBe(1)
  })

  it('トランザクション中断時は行も D1 も消費しない', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }
    const countBefore = await queue.countSlots()
    const nextD1Before = await queue.readNextD1(scope)

    await expect(
      queue.append(
        appendInput(scope, {
          event: { fields: { V7: () => undefined } },
        }),
      ),
    ).rejects.toBeDefined()

    expect(await queue.countSlots()).toBe(countBefore)
    expect(await queue.readNextD1(scope)).toBe(nextD1Before)
    expect((await queue.append(appendInput(scope))).d1).toBe(nextD1Before)
  })

  it('追記と D1 カウンタを 1 回の readwrite トランザクションで永続化する', async () => {
    const queue = await openTestQueue()
    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')

    await queue.append(appendInput({ game: 'game-a', d4: 'generation-a' }))

    expect(transactionSpy).toHaveBeenCalledTimes(1)
    expect(transactionSpy).toHaveBeenCalledWith(
      expect.arrayContaining(['queue', 'd1-counters']),
      'readwrite',
    )
  })

  it('D7 はオンライン確認なしのローカル経路で既存 D1 を保つ', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue({ allocateNextD1: allocator })
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await queue.append(appendInput(scope))
    allocator.mockClear()
    const newD5 = { value: 'new-d5' }

    const replacement = await queue.replaceRevision({
      kind: 'D7',
      scope,
      d1: original.d1,
      d5: newD5,
      version: { value: 'new-version' },
      event: { fields: {} },
    })

    expect(allocator).not.toHaveBeenCalled()
    expect(replacement.d1).toBe(original.d1)
    expect(replacement.d5).toBe(newD5)
    expect(replacement.state).toBe(queueStateId('未送信'))
    expect(await queue.countSlots()).toBe(1)
    expect(await queue.readSlot(scope, original.d1)).toEqual(replacement)
  })

  it('K5 は確認・生成・空内容置換を 1 回のトランザクションで行い D1 を採番しない', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue({ allocateNextD1: allocator })
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await queue.append(
      appendInput(scope, { d5: 'old-d5', event: { fields: { V7: {} } } }),
    )
    const source: DurableQueueSlot = {
      ...original,
      state: queueStateId('要操作'),
      actionRequiredLabel: actionRequiredLabelId('墓標待ち'),
    }
    await overwriteQueueSlot(databaseName, source)
    allocator.mockClear()
    const replacementD1Allocator = vi.fn(() => source.d1 + 1)
    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')

    const result = await queue.replaceWithTombstone(
      {
        kind: 'D6',
        scope,
        d1: source.d1,
        tombstoneVersion: 'tombstone-version',
        boundaryRequest: tombstoneBoundaryRequest(source),
      },
      successfulTombstoneInjections('new-d5', {
        allocateD1: replacementD1Allocator,
      }),
    )

    expect(result.offered).toBe(true)
    expect(transactionSpy).toHaveBeenCalledTimes(1)
    expect(transactionSpy).toHaveBeenCalledWith('queue', 'readwrite')
    expect(allocator).not.toHaveBeenCalled()
    expect(replacementD1Allocator).not.toHaveBeenCalled()
    if (!result.offered) {
      throw new Error('墓標置換がありません')
    }
    expect(result.replacement.d1).toBe(source.d1)
    expect(result.replacement.d5).toBe('new-d5')
    expect(Reflect.ownKeys(result.replacement.event.fields)).toHaveLength(0)
    expect(result.replacement.state).toBe(queueStateId('未送信'))
    transactionSpy.mockRestore()
    expect(await queue.readSlot(scope, source.d1)).toEqual(result.replacement)
  })

  it.each([
    ['別イベント', 'new-d5', { game: 'game-b' }],
    ['D5 が undefined', undefined, {}],
    ['既存 D5 と同一', 'old-d5', {}],
  ] as const)(
    'K5 は%sなら永続スロットを変更しない',
    async (_name, newD5, boundaryOverrides) => {
      const queue = await openTestQueue()
      const databaseName = databaseNames.at(-1)
      if (!databaseName) {
        throw new Error('テスト DB 名がありません')
      }
      const scope = { game: 'game-a', d4: 'generation-a' }
      const original = await queue.append(appendInput(scope, { d5: 'old-d5' }))
      const source: DurableQueueSlot = {
        ...original,
        state: queueStateId('要操作'),
        actionRequiredLabel: actionRequiredLabelId('墓標待ち'),
      }
      await overwriteQueueSlot(databaseName, source)

      const result = await queue.replaceWithTombstone(
        {
          kind: 'D6',
          scope,
          d1: source.d1,
          tombstoneVersion: {},
          boundaryRequest: tombstoneBoundaryRequest(source, boundaryOverrides),
        },
        successfulTombstoneInjections(newD5),
      )

      expect(result.offered).toBe(false)
      expect(await queue.readSlot(scope, source.d1)).toEqual(source)
    },
  )

  it('K5 の低水準準備だけでは永続スロットを置換できない', async () => {
    const queue = await openTestQueue()
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await queue.append(appendInput(scope, { d5: 'old-d5' }))
    const source: DurableQueueSlot = {
      ...original,
      state: queueStateId('要操作'),
      actionRequiredLabel: actionRequiredLabelId('墓標待ち'),
    }
    await overwriteQueueSlot(databaseName, source)

    const prepared = prepareTombstoneReplacement(
      {
        slot: source,
        tombstoneVersion: {},
        boundaryRequest: tombstoneBoundaryRequest(source),
      },
      successfulTombstoneInjections('new-d5'),
    )

    expect(prepared.offered).toBe(true)
    expect(await queue.readSlot(scope, source.d1)).toEqual(source)
  })

  it('置換の永続化に失敗した場合は既存スロットを保つ', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await queue.append(appendInput(scope))

    await expect(
      queue.replaceRevision({
        kind: 'D7',
        scope,
        d1: original.d1,
        d5: { value: 'new-d5' },
        version: { value: 'new-version' },
        event: { fields: { V7: () => undefined } },
      }),
    ).rejects.toBeDefined()

    expect(await queue.readSlot(scope, original.d1)).toEqual(original)
    expect(await queue.countSlots()).toBe(1)
  })

  it('IndexedDB が無い場合は記録開始を拒否する', async () => {
    await expect(
      openDurableQueue({
        databaseName: nextDatabaseName(),
        indexedDbFactory: null,
        requestStoragePersistence: async () => true,
      }),
    ).rejects.toBeInstanceOf(DurableQueueUnavailableError)
  })

  it('IndexedDB の open が失敗した場合は記録開始を拒否する', async () => {
    const databaseName = nextDatabaseName()
    const versionTwoRequest = indexedDB.open(databaseName, 2)
    const versionTwoDatabase = await new Promise<IDBDatabase>(
      (resolve, reject) => {
        versionTwoRequest.onsuccess = () => resolve(versionTwoRequest.result)
        versionTwoRequest.onerror = () => reject(versionTwoRequest.error)
      },
    )
    versionTwoDatabase.close()

    await expect(
      openDurableQueue({
        databaseName,
        requestStoragePersistence: async () => true,
      }),
    ).rejects.toBeInstanceOf(DurableQueueUnavailableError)
  })

  it('structured clone で undefined のプロパティを失わず往復する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }
    const appended = await queue.append(
      appendInput(scope, {
        event: { fields: { V7: { retained: undefined } } },
      }),
    )

    const stored = await queue.readSlot(scope, appended.d1)
    const payload = stored?.event.fields.V7 as { retained?: unknown }
    expect(Object.hasOwn(payload, 'retained')).toBe(true)
    expect(payload.retained).toBeUndefined()
    expect(durableQueueSource).not.toContain('JSON.stringify')
  })

  it('storage.persist の結果を保持して返す', async () => {
    const persist = vi
      .fn(async () => true)
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
    vi.stubGlobal('navigator', { storage: { persist } })
    const grantedQueue = await openTestQueue({
      requestStoragePersistence: undefined,
    })
    const rejectedQueue = await openTestQueue({
      requestStoragePersistence: undefined,
    })

    expect(persist).toHaveBeenCalledTimes(2)
    expect(grantedQueue.storagePersistenceGranted).toBe(true)
    expect(rejectedQueue.storagePersistenceGranted).toBe(false)
  })
})

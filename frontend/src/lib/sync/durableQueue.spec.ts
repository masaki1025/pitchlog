import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import durableQueueSource from './durableQueue.ts?raw'
import * as durableQueueModule from './durableQueue'
import {
  DurableQueueUnavailableError,
  openDurableQueue,
  type D1Allocator,
  type DurableI6Slot,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
  type DurableQueueSlot,
  type I6AcceptedAtResolution,
} from './durableQueue'
import { REQUEST_ONLY_IDS, SYNC_EVENT_PATH } from './eventFieldRules'
import {
  prepareTombstoneReplacement,
  TOMBSTONE_ONLINE_STATE,
  type TombstoneBoundaryRequest,
  type TombstoneGenerationInjections,
} from './k5Tombstone'
import {
  actionRequiredLabelId,
  I6_HOLDING_CONTRACT,
  queueStateId,
  type I6Acceptance,
} from './queueState'
import { evaluateQueueTransition, RG1_STATE } from './queueTransition'
import {
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type TargetEventReference,
} from './syncEvent'

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

function targetReference(
  overrides: Partial<TargetEventReference> = {},
): TargetEventReference {
  return {
    ...Object.fromEntries(
      TARGET_EVENT_REFERENCE_ELEMENTS.map((element, index) => [
        element,
        `target-${index}`,
      ]),
    ),
    ...overrides,
  } as TargetEventReference
}

function i6Acceptance(overrides: Partial<I6Acceptance> = {}): I6Acceptance {
  return {
    targetReference: targetReference(),
    expectedVersion: 'expected-version',
    d5: 'i6-d5',
    confirmedContent: 'confirmed-content',
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

  it('I6 の5要素を 1 回のトランザクションで不可分に永続化する', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const acceptedAt = 'first-accepted-at'
    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')

    const receipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt,
      }),
    })

    expect(receipt).toBeDefined()
    expect(transactionSpy).toHaveBeenCalledTimes(1)
    expect(transactionSpy).toHaveBeenCalledWith('i6-results', 'readwrite')
    if (!receipt) {
      throw new Error('I6 永続化 receipt がありません')
    }
    const expectedSlot: DurableI6Slot = {
      targetReference: acceptance.targetReference,
      expectedVersion: acceptance.expectedVersion,
      d5: acceptance.d5,
      confirmedContent: acceptance.confirmedContent,
      acceptedAt,
      source: 'p3-acceptance',
      state: queueStateId('同期済み'),
    }
    expect(receipt.slot).toEqual(expectedSlot)
    transactionSpy.mockRestore()
    expect(await queue.readI6(acceptance.d5)).toEqual(expectedSlot)
  })

  it.each([
    ['未注入', {}],
    ['不明', { resolveAcceptedAt: () => ({ known: false as const }) }],
    [
      'undefined',
      {
        resolveAcceptedAt: (acceptance: I6Acceptance) => ({
          known: true as const,
          targetReference: acceptance.targetReference,
          acceptedAt: undefined,
        }),
      },
    ],
    [
      '旧形の value: undefined',
      {
        resolveAcceptedAt: () =>
          ({
            known: true,
            value: undefined,
          }) as unknown as I6AcceptedAtResolution,
      },
    ],
    [
      '例外',
      {
        resolveAcceptedAt: () => {
          throw new Error('応答解決失敗')
        },
      },
    ],
  ] as const)(
    'accepted_at が%sなら I6 を永続化しない',
    async (_name, injections) => {
      const queue = await openTestQueue()
      const acceptance = i6Acceptance()

      const receipt = await queue.persistI6Acceptance(acceptance, injections)

      expect(receipt).toBeUndefined()
      expect(await queue.readI6(acceptance.d5)).toBeUndefined()
    },
  )

  it('accepted_at の応答が別イベントを指す場合は I6 を永続化しない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const changedElement = TARGET_EVENT_REFERENCE_ELEMENTS[0]
    const otherTarget = targetReference({ [changedElement]: 'other-target' })

    const receipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: otherTarget,
        acceptedAt: {},
      }),
    })

    expect(receipt).toBeUndefined()
    expect(await queue.readI6(acceptance.d5)).toBeUndefined()
  })

  it('保存済み I6 の再掲では初回の accepted_at を上書きしない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance({
      confirmedContent: { result: '確定内容' },
    })
    const firstReceipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'first-accepted-at',
      }),
    })
    const replayAcceptance = structuredClone(acceptance)
    const replayReceipt = await queue.persistI6Acceptance(replayAcceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: replayAcceptance.targetReference,
        acceptedAt: 'replayed-accepted-at',
      }),
    })

    expect(firstReceipt?.slot.acceptedAt).toBe('first-accepted-at')
    expect(replayReceipt?.slot.acceptedAt).toBe('first-accepted-at')
    expect((await queue.readI6(acceptance.d5))?.acceptedAt).toBe(
      'first-accepted-at',
    )
  })

  it('I6 の永続化失敗時は receipt も保存済み結果も残さない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance({ confirmedContent: () => undefined })

    await expect(
      queue.persistI6Acceptance(acceptance, {
        resolveAcceptedAt: () => ({
          known: true,
          targetReference: acceptance.targetReference,
          acceptedAt: {},
        }),
      }),
    ).rejects.toBeDefined()

    expect(await queue.readI6(acceptance.d5)).toBeUndefined()
  })

  it('保存済み I6 を退避済みにしても5要素を保持し、直接閲覧・書き出しできる', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const receipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'accepted-at',
      }),
    })
    if (!receipt) {
      throw new Error('I6 永続化 receipt がありません')
    }

    const evacuated = await queue.evacuateI6(acceptance.d5)

    expect(evacuated).toEqual({
      ...receipt.slot,
      state: queueStateId('退避済み'),
    })
    expect(await queue.readI6(acceptance.d5)).toEqual(evacuated)
    expect(JSON.parse(JSON.stringify(evacuated))).toEqual(evacuated)
  })

  it('I6 の11トークンを実際の保持・遷移・破棄構造へ1対1で対応づける', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const firstReceipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'first-accepted-at',
      }),
    })
    const replayReceipt = await queue.persistI6Acceptance(acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'replayed-accepted-at',
      }),
    })
    if (!firstReceipt || !replayReceipt) {
      throw new Error('I6 永続化 receipt がありません')
    }
    const notExpired = evaluateQueueTransition(
      {
        kind: 'discard',
        slot: firstReceipt.slot,
        confirmed24HoursElapsed: false,
      },
      { resolveRg1State: () => RG1_STATE.INACTIVE_CONFIRMED },
    )
    const blockedDuringRg1 = evaluateQueueTransition(
      {
        kind: 'discard',
        slot: firstReceipt.slot,
        confirmed24HoursElapsed: true,
      },
      { resolveRg1State: () => RG1_STATE.ACTIVE },
    )
    let persistenceFailed = false
    const lostAcceptance = i6Acceptance({
      d5: 'lost-i6-d5',
      confirmedContent: () => undefined,
    })
    try {
      await queue.persistI6Acceptance(lostAcceptance, {
        resolveAcceptedAt: () => ({
          known: true,
          targetReference: lostAcceptance.targetReference,
          acceptedAt: 'lost-accepted-at',
        }),
      })
    } catch {
      persistenceFailed = true
    }
    const lostStoredResult = await queue.readI6(lostAcceptance.d5)
    const transitionEvacuation = evaluateQueueTransition(
      { kind: 'i6-evacuation-saved', slot: firstReceipt.slot },
      { confirmI6EvacuationSaved: () => true },
    )
    const durableEvacuation = await queue.evacuateI6(acceptance.d5)
    const viewedResult = await queue.readI6(acceptance.d5)
    const writtenResult = JSON.parse(JSON.stringify(viewedResult)) as unknown
    const implementationAssertions = [
      () =>
        expect(firstReceipt.slot.targetReference).toEqual(
          acceptance.targetReference,
        ),
      () =>
        expect(firstReceipt.slot.expectedVersion).toBe(
          acceptance.expectedVersion,
        ),
      () => expect(firstReceipt.slot.d5).toBe(acceptance.d5),
      () =>
        expect(firstReceipt.slot.confirmedContent).toBe(
          acceptance.confirmedContent,
        ),
      () => expect(firstReceipt.slot.acceptedAt).toBe('first-accepted-at'),
      () => expect(notExpired.applied).toBe(false),
      () => expect(replayReceipt.slot.acceptedAt).toBe('first-accepted-at'),
      () => {
        expect(persistenceFailed).toBe(true)
        expect(lostStoredResult).toBeUndefined()
      },
      () => expect(blockedDuringRg1.applied).toBe(false),
      () => {
        expect(transitionEvacuation.applied).toBe(true)
        if (transitionEvacuation.applied) {
          expect(transitionEvacuation.slot).toEqual({
            ...firstReceipt.slot,
            state: queueStateId('退避済み'),
          })
        }
        expect(durableEvacuation?.state).toBe(queueStateId('退避済み'))
        expect(viewedResult).toEqual(durableEvacuation)
        expect(writtenResult).toEqual(durableEvacuation)
      },
      () =>
        expect(
          Object.keys(durableQueueModule).filter((name) =>
            /recover|reapply|restore/i.test(name),
          ),
        ).toEqual([]),
    ] as const

    expect(implementationAssertions).toHaveLength(
      I6_HOLDING_CONTRACT.elements.length,
    )
    for (const [index, assertion] of implementationAssertions.entries()) {
      expect(I6_HOLDING_CONTRACT.elements[index]).toBeDefined()
      assertion()
    }
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
    const newerVersionRequest = indexedDB.open(databaseName, 3)
    const newerVersionDatabase = await new Promise<IDBDatabase>(
      (resolve, reject) => {
        newerVersionRequest.onsuccess = () =>
          resolve(newerVersionRequest.result)
        newerVersionRequest.onerror = () => reject(newerVersionRequest.error)
      },
    )
    newerVersionDatabase.close()

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

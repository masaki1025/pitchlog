import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import durableQueueSource from './durableQueue.ts?raw'
import * as durableQueueModule from './durableQueue'
import {
  DurableQueueUnavailableError,
  I6EvacuationReceipt,
  openDurableQueue,
  type D1Allocator,
  type DurableI6Slot,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
  type DurableQueueSlot,
  type I6AcceptedAtResolution,
} from './durableQueue'
import {
  EVENT_KIND_SLOT_ID,
  REQUEST_ONLY_IDS,
  SYNC_EVENT_PATH,
} from './eventFieldRules'
import { EVENT_KIND_RULES } from './eventKinds'
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

async function appendToQueue(
  queue: DurableQueue,
  input: DurableQueueAppend,
): Promise<DurableQueueSlot> {
  return queue.append(queue.prepareAppend(input))
}

async function persistI6(
  queue: DurableQueue,
  acceptance: I6Acceptance,
  injections: Parameters<DurableQueue['prepareI6Acceptance']>[1] = {},
) {
  const preparation = queue.prepareI6Acceptance(acceptance, injections)
  return preparation
    ? queue.persistI6Acceptance(preparation)
    : Promise.resolve(undefined)
}

const REVISION_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name === '改訂版',
)
if (!REVISION_EVENT_KIND) {
  throw new Error('改訂版のイベント種別がありません')
}
const REVISION_EVENT_KIND_ID = REVISION_EVENT_KIND.id

function revisionEvent(): DurableQueueAppend['event'] {
  return { fields: { [EVENT_KIND_SLOT_ID]: REVISION_EVENT_KIND_ID } }
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

    const first = await appendToQueue(queue, appendInput(scope))
    const second = await appendToQueue(queue, appendInput(scope))
    const third = await appendToQueue(queue, appendInput(scope))

    expect([first.d1, second.d1, third.d1]).toEqual([1, 2, 3])
    expect(await queue.readNextD1(scope)).toBe(4)
  })

  it('別の (試合, D4) の D1 カウンタを独立させる', async () => {
    const queue = await openTestQueue()
    const firstScope = { game: 'game-a', d4: 'generation-a' }
    const secondScope = { game: 'game-a', d4: 'generation-b' }
    const thirdScope = { game: 'game-b', d4: 'generation-a' }

    await appendToQueue(queue, appendInput(firstScope))
    await appendToQueue(queue, appendInput(firstScope))
    const secondFirst = await appendToQueue(queue, appendInput(secondScope))
    const thirdFirst = await appendToQueue(queue, appendInput(thirdScope))

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
      appendToQueue(
        queue,
        appendInput(scope, {
          event: { fields: { V7: () => undefined } },
        }),
      ),
    ).rejects.toBeDefined()

    expect(await queue.countSlots()).toBe(countBefore)
    expect(await queue.readNextD1(scope)).toBe(nextD1Before)
    expect((await appendToQueue(queue, appendInput(scope))).d1).toBe(
      nextD1Before,
    )
  })

  it('追記と D1 カウンタを 1 回の readwrite トランザクションで永続化する', async () => {
    const queue = await openTestQueue()
    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')

    await appendToQueue(
      queue,
      appendInput({ game: 'game-a', d4: 'generation-a' }),
    )

    expect(transactionSpy).toHaveBeenCalledTimes(1)
    expect(transactionSpy).toHaveBeenCalledWith(
      expect.arrayContaining(['queue', 'd1-counters']),
      'readwrite',
    )
  })

  it('状態 index で未送信だけを数える', async () => {
    const queue = await openTestQueue()
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const scope = { game: 'game-a', d4: 'generation-a' }
    const states = [
      queueStateId('未送信'),
      queueStateId('要操作'),
      queueStateId('同期済み'),
      queueStateId('退避済み'),
    ] as const

    for (const [index, state] of states.entries()) {
      const slot = await appendToQueue(
        queue,
        appendInput(scope, { d5: `state-${index}` }),
      )
      await overwriteQueueSlot(databaseName, { ...slot, state })
    }

    expect(await queue.countSlots()).toBe(states.length)
    expect(await queue.countUnsentSlots()).toBe(1)
  })

  it('I6 の5要素を 1 回のトランザクションで不可分に永続化する', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const acceptedAt = 'first-accepted-at'
    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')

    const receipt = await persistI6(queue, acceptance, {
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

      const receipt = await persistI6(queue, acceptance, injections)

      expect(receipt).toBeUndefined()
      expect(await queue.readI6(acceptance.d5)).toBeUndefined()
    },
  )

  it('accepted_at の応答が別イベントを指す場合は I6 を永続化しない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const changedElement = TARGET_EVENT_REFERENCE_ELEMENTS[0]
    const otherTarget = targetReference({ [changedElement]: 'other-target' })

    const receipt = await persistI6(queue, acceptance, {
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
    const acceptance = i6Acceptance()
    const firstReceipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'first-accepted-at',
      }),
    })
    const replayAcceptance = structuredClone(acceptance)
    const replayReceipt = await persistI6(queue, replayAcceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: replayAcceptance.targetReference,
        acceptedAt: 'first-accepted-at',
      }),
    })

    expect(firstReceipt?.slot.acceptedAt).toBe('first-accepted-at')
    expect(replayReceipt?.slot.acceptedAt).toBe('first-accepted-at')
    expect((await queue.readI6(acceptance.d5))?.acceptedAt).toBe(
      'first-accepted-at',
    )
  })

  it('I6 receipt の matches は5要素すべてに結合する', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const receipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'accepted-at',
      }),
    })
    if (!receipt) {
      throw new Error('I6 永続化 receipt がありません')
    }
    const snapshot = receipt.slot
    const targetElement = TARGET_EVENT_REFERENCE_ELEMENTS[0]

    expect(receipt.matches(snapshot)).toBe(true)
    expect(
      receipt.matches({
        ...snapshot,
        targetReference: {
          ...snapshot.targetReference,
          [targetElement]: 'different-target',
        },
      }),
    ).toBe(false)
    expect(
      receipt.matches({ ...snapshot, expectedVersion: 'different-version' }),
    ).toBe(false)
    expect(receipt.matches({ ...snapshot, d5: 'different-d5' })).toBe(false)
    expect(
      receipt.matches({ ...snapshot, confirmedContent: 'different-content' }),
    ).toBe(false)
    expect(
      receipt.matches({ ...snapshot, acceptedAt: 'different-accepted-at' }),
    ).toBe(false)
  })

  it('I6 の永続化失敗時は receipt も保存済み結果も残さない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance({ confirmedContent: () => undefined })

    await expect(
      persistI6(queue, acceptance, {
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
    const receipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'accepted-at',
      }),
    })
    if (!receipt) {
      throw new Error('I6 永続化 receipt がありません')
    }

    const evacuationReceipt = await queue.prepareI6Evacuation(acceptance.d5, {
      confirmI6EvacuationSaved: () => true,
    })
    if (!evacuationReceipt) {
      throw new Error('I6 の退避保存 receipt がありません')
    }
    const evacuated = await queue.evacuateI6(evacuationReceipt)

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
    const firstReceipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'first-accepted-at',
      }),
    })
    const replayReceipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'first-accepted-at',
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
      await persistI6(queue, lostAcceptance, {
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
    const evacuationReceipt = await queue.prepareI6Evacuation(acceptance.d5, {
      confirmI6EvacuationSaved: () => true,
    })
    const transitionEvacuation = evaluateQueueTransition({
      kind: 'i6-evacuation-saved',
      evacuationReceipt,
    })
    const durableEvacuation = evacuationReceipt
      ? await queue.evacuateI6(evacuationReceipt)
      : undefined
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

  it('D7 は改訂待ちの要操作スロットだけを同じトランザクションで置換する', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue({ allocateNextD1: allocator })
    const scope = { game: 'game-a', d4: 'generation-a' }
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const original = await appendToQueue(queue, appendInput(scope))
    await overwriteQueueSlot(databaseName, {
      ...original,
      state: queueStateId('要操作'),
      actionRequiredLabel: actionRequiredLabelId('改訂待ち'),
    })
    allocator.mockClear()
    const newD5 = { value: 'new-d5' }

    const transactionSpy = vi.spyOn(IDBDatabase.prototype, 'transaction')
    const replacement = await queue.replaceRevision(
      queue.prepareRevisionReplacement({
        scope,
        d1: original.d1,
        d5: newD5,
        version: { value: 'new-version' },
        event: revisionEvent(),
      }),
    )

    expect(allocator).not.toHaveBeenCalled()
    expect(replacement.d1).toBe(original.d1)
    expect(replacement.d5).toEqual(newD5)
    expect(replacement.state).toBe(queueStateId('未送信'))
    expect(transactionSpy).toHaveBeenCalledTimes(1)
    expect(transactionSpy).toHaveBeenCalledWith('queue', 'readwrite')
    transactionSpy.mockRestore()
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
    const original = await appendToQueue(
      queue,
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
      queue.prepareTombstoneReplacement(
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
      ),
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
      const original = await appendToQueue(
        queue,
        appendInput(scope, { d5: 'old-d5' }),
      )
      const source: DurableQueueSlot = {
        ...original,
        state: queueStateId('要操作'),
        actionRequiredLabel: actionRequiredLabelId('墓標待ち'),
      }
      await overwriteQueueSlot(databaseName, source)

      const result = await queue.replaceWithTombstone(
        queue.prepareTombstoneReplacement(
          {
            kind: 'D6',
            scope,
            d1: source.d1,
            tombstoneVersion: {},
            boundaryRequest: tombstoneBoundaryRequest(
              source,
              boundaryOverrides,
            ),
          },
          successfulTombstoneInjections(newD5),
        ),
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
    const original = await appendToQueue(
      queue,
      appendInput(scope, { d5: 'old-d5' }),
    )
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
    const original = await appendToQueue(queue, appendInput(scope))

    await expect(
      Promise.resolve().then(() =>
        queue.replaceRevision(
          queue.prepareRevisionReplacement({
            scope,
            d1: original.d1,
            d5: { value: 'new-d5' },
            version: { value: 'new-version' },
            event: {
              fields: {
                [EVENT_KIND_SLOT_ID]: REVISION_EVENT_KIND_ID,
                V7: () => undefined,
              },
            },
          }),
        ),
      ),
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
    const newerVersionRequest = indexedDB.open(databaseName, 4)
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
    const appended = await appendToQueue(
      queue,
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

  it.each([
    ['未送信', queueStateId('未送信'), undefined],
    ['墓標待ち', queueStateId('要操作'), actionRequiredLabelId('墓標待ち')],
  ] as const)(
    'D7 は%sのスロットを上書きしない',
    async (_name, state, actionRequiredLabel) => {
      const queue = await openTestQueue()
      const databaseName = databaseNames.at(-1)
      if (!databaseName) {
        throw new Error('テスト DB 名がありません')
      }
      const scope = { game: 'game-a', d4: 'generation-a' }
      const original = await appendToQueue(queue, appendInput(scope))
      const source = { ...original, state, actionRequiredLabel }
      await overwriteQueueSlot(databaseName, source)

      await expect(
        queue.replaceRevision(
          queue.prepareRevisionReplacement({
            scope,
            d1: original.d1,
            d5: 'new-d5',
            version: 'new-version',
            event: revisionEvent(),
          }),
        ),
      ).rejects.toThrow('改訂待ち')
      expect(await queue.readSlot(scope, original.d1)).toEqual(source)
    },
  )

  it('D7 は既存 D5 と同一の置換を拒否する', async () => {
    const queue = await openTestQueue()
    const databaseName = databaseNames.at(-1)
    if (!databaseName) {
      throw new Error('テスト DB 名がありません')
    }
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await appendToQueue(
      queue,
      appendInput(scope, { d5: 'same-d5' }),
    )
    const source = {
      ...original,
      state: queueStateId('要操作'),
      actionRequiredLabel: actionRequiredLabelId('改訂待ち'),
    }
    await overwriteQueueSlot(databaseName, source)

    await expect(
      queue.replaceRevision(
        queue.prepareRevisionReplacement({
          scope,
          d1: original.d1,
          d5: original.d5,
          version: 'new-version',
          event: revisionEvent(),
        }),
      ),
    ).rejects.toThrow('新しい D5')
    expect(await queue.readSlot(scope, original.d1)).toEqual(source)
  })

  it('D7 を名乗る空内容を preparation にできない', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game-a', d4: 'generation-a' }
    const original = await appendToQueue(queue, appendInput(scope))

    expect(() =>
      queue.prepareRevisionReplacement({
        scope,
        d1: original.d1,
        d5: 'new-d5',
        version: 'new-version',
        event: { fields: {} },
      }),
    ).toThrow('実際の改訂版')
    expect(await queue.readSlot(scope, original.d1)).toEqual(original)
  })

  it('I6 receipt の公開スナップショットを書き換えても遷移内容は変わらない', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    const receipt = await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'accepted-at',
      }),
    })
    if (!receipt) {
      throw new Error('I6 永続化 receipt がありません')
    }
    const exposed = receipt.slot as {
      expectedVersion: unknown
      confirmedContent: unknown
    }
    exposed.expectedVersion = 'tampered-version'
    exposed.confirmedContent = 'tampered-content'

    const transition = evaluateQueueTransition({
      kind: 'p3-acceptance-persisted',
      persistenceReceipt: receipt,
    })

    expect(transition.applied).toBe(true)
    if (transition.applied && transition.slot?.source === 'p3-acceptance') {
      expect(transition.slot.expectedVersion).toBe(acceptance.expectedVersion)
      expect(transition.slot.confirmedContent).toBe(acceptance.confirmedContent)
    }
  })

  it.each([
    ['V11', { expectedVersion: 'different-version' }],
    ['確定内容', { confirmedContent: 'different-content' }],
  ] as const)(
    '同じ対象・D5 でも%sが異なる I6 には receipt を返さない',
    async (_name, overrides) => {
      const queue = await openTestQueue()
      const acceptance = i6Acceptance()
      const injections = {
        resolveAcceptedAt: (input: I6Acceptance) => ({
          known: true as const,
          targetReference: input.targetReference,
          acceptedAt: 'accepted-at',
        }),
      }
      expect(await persistI6(queue, acceptance, injections)).toBeDefined()
      expect(
        await persistI6(queue, { ...acceptance, ...overrides }, injections),
      ).toBeUndefined()
    },
  )

  it('I6 は D5 だけでは退避できず、保存完了 receipt と5要素の一致を要求する', async () => {
    const queue = await openTestQueue()
    const acceptance = i6Acceptance()
    await persistI6(queue, acceptance, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: acceptance.targetReference,
        acceptedAt: 'accepted-at',
      }),
    })

    // @ts-expect-error D5 は退避変更 API の入力ではない。
    await expect(queue.evacuateI6(acceptance.d5)).rejects.toThrow('receipt')
    expect(
      await queue.prepareI6Evacuation(acceptance.d5, {
        confirmI6EvacuationSaved: () => false,
      }),
    ).toBeUndefined()
    expect((await queue.readI6(acceptance.d5))?.state).toBe(
      queueStateId('同期済み'),
    )
    const invalidReceipt = () => {
      // @ts-expect-error 退避保存 receipt は直接生成できない。
      return new I6EvacuationReceipt({} as DurableI6Slot, Symbol('forged'))
    }
    expect(invalidReceipt).toBeTypeOf('function')
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

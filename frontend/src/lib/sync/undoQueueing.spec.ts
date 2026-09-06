import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  openDurableQueue,
  type D1Allocator,
  type DurableQueue,
  type DurableQueueScope,
} from './durableQueue'
import {
  EVENT_FIELD_RULES,
  EVENT_KIND_SLOT_ID,
  isCancellableEventKind,
  type EventFieldRule,
  type EventSlotId,
} from './eventFieldRules'
import { EVENT_KIND_RULES } from './eventKinds'
import {
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'
import undoQueueingSource from './undoQueueing.ts?raw'
import {
  queueUndoEvent,
  type UndoOperationResolver,
  type UndoQueueingRequest,
} from './undoQueueing'

const UNDO_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name === 'undo',
)
type CompositeFieldRule = Extract<
  EventFieldRule,
  { shape: { kind: 'composite' } }
>
const TARGET_REFERENCE_RULE = EVENT_FIELD_RULES.find(
  (rule): rule is CompositeFieldRule => rule.shape.kind === 'composite',
)
const STATE_DIFF_RULE = EVENT_FIELD_RULES.find((rule) =>
  rule.conditions.some((condition) => condition === '取消可能な操作に限る'),
)
if (!UNDO_EVENT_KIND || !TARGET_REFERENCE_RULE || !STATE_DIFF_RULE) {
  throw new Error('undo の検査に必要なイベント規則がありません')
}
const STATE_DIFF_SLOT_ID = STATE_DIFF_RULE.id as EventSlotId

let databaseSequence = 0
const openedQueues: DurableQueue[] = []
const databaseNames: string[] = []

async function openTestQueue(
  allocateNextD1?: D1Allocator,
): Promise<DurableQueue> {
  databaseSequence += 1
  const databaseName = `undo-queueing-${databaseSequence}`
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => false,
    ...(allocateNextD1 ? { allocateNextD1 } : {}),
  })
  openedQueues.push(queue)
  databaseNames.push(databaseName)
  return queue
}

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('テスト DB を削除できません'))
  })
}

function targetReference(
  game: unknown,
  d4: unknown,
  d1: unknown,
): TargetEventReference {
  const values = [game, d4, d1]
  return Object.fromEntries(
    TARGET_EVENT_REFERENCE_ELEMENTS.map((element, index) => [
      element,
      values[index],
    ]),
  ) as TargetEventReference
}

function request(
  queue: DurableQueue,
  scope: DurableQueueScope,
  event: SyncEvent = { fields: {} },
): UndoQueueingRequest {
  return {
    queue,
    scope,
    d5: 'undo-d5',
    version: 'undo-version',
    event,
  }
}

afterEach(async () => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  for (const name of databaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

describe('undoQueueing', () => {
  it('ローカルに残る対象にも常に新しい undo イベントを追記する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game', d4: 'current-generation' }
    const targetSlot = await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'target-d5',
        version: 'target-version',
        event: { fields: {} },
      }),
    )
    const target = targetReference(
      targetSlot.game,
      targetSlot.d4,
      targetSlot.d1,
    )
    const operationResult = Object.freeze({ source: 'game-state' })

    const result = await queueUndoEvent(request(queue, scope), {
      resolveUndoOperation: () => ({
        targetReference: target,
        operationResult,
      }),
    })

    expect(result?.operationResult).toBe(operationResult)
    expect(result?.slot).toMatchObject({
      game: scope.game,
      d4: scope.d4,
      d1: targetSlot.d1 + 1,
      d5: 'undo-d5',
      version: 'undo-version',
    })
    expect(result?.slot?.event.fields[EVENT_KIND_SLOT_ID]).toBe(
      UNDO_EVENT_KIND.id,
    )
    expect(result?.slot?.event.fields[TARGET_REFERENCE_RULE.id]).toEqual(target)
  })

  it('ローカルに対象スロットが無くても注入された参照へ undo を追記する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game', d4: 'current-generation' }
    const target = targetReference('game', 'past-generation', 1)

    const result = await queueUndoEvent(request(queue, scope), {
      resolveUndoOperation: () => ({
        targetReference: target,
        operationResult: 'injected-result',
      }),
    })

    expect(result?.slot?.d1).toBe(1)
    expect(result?.slot?.event.fields[TARGET_REFERENCE_RULE.id]).toEqual(target)
    expect(await queue.countSlots()).toBe(1)
  })

  it('対象を試合・対象 D4・対象 D1 の組で保持する', async () => {
    const queue = await openTestQueue()
    const scope = { game: 'game', d4: 'generation' }
    const target = targetReference({}, {}, {})

    const result = await queueUndoEvent(request(queue, scope), {
      resolveUndoOperation: () => ({
        targetReference: target,
        operationResult: {},
      }),
    })
    const storedTarget = result?.slot?.event.fields[TARGET_REFERENCE_RULE.id]

    expect(Reflect.ownKeys(storedTarget as object)).toEqual(
      TARGET_EVENT_REFERENCE_ELEMENTS,
    )
    expect(storedTarget).toEqual(target)
  })

  it('取消対象の注入が無ければ fail-closed で投入しない', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue(allocator)

    await expect(
      queueUndoEvent(request(queue, { game: 'game', d4: 'generation' })),
    ).resolves.toBeUndefined()
    expect(allocator).not.toHaveBeenCalled()
    expect(await queue.countSlots()).toBe(0)
  })

  it('状況計算の注入が例外なら fail-closed で投入しない', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue(allocator)
    const resolver: UndoOperationResolver = () => {
      throw new Error('状況計算失敗')
    }

    await expect(
      queueUndoEvent(request(queue, { game: 'game', d4: 'generation' }), {
        resolveUndoOperation: resolver,
      }),
    ).resolves.toBeUndefined()
    expect(allocator).not.toHaveBeenCalled()
    expect(await queue.countSlots()).toBe(0)
  })

  it('空履歴の対象なしではイベントを生成せず D1 も消費しない', async () => {
    const allocator = vi.fn<D1Allocator>((previousD1) => previousD1 + 1)
    const queue = await openTestQueue(allocator)
    const operationResult = Object.freeze({ source: 'game-state-empty' })

    const result = await queueUndoEvent(
      request(queue, { game: 'game', d4: 'generation' }),
      {
        resolveUndoOperation: () => ({
          targetReference: undefined,
          operationResult,
        }),
      },
    )

    expect(result).toEqual({ operationResult })
    expect(Object.hasOwn(result ?? {}, 'slot')).toBe(false)
    expect(allocator).not.toHaveBeenCalled()
    expect(await queue.countSlots()).toBe(0)
  })

  it('注入された操作結果の値を解釈せずそのまま返す', async () => {
    const queue = await openTestQueue()
    const operationResult = new Proxy(
      {},
      {
        get() {
          throw new Error('操作結果の内部を読みました')
        },
        ownKeys() {
          throw new Error('操作結果の内部キーを読みました')
        },
      },
    )

    const result = await queueUndoEvent(
      request(queue, { game: 'game', d4: 'generation' }),
      {
        resolveUndoOperation: () => ({
          targetReference: targetReference('game', 'generation', 1),
          operationResult,
        }),
      },
    )

    expect(result?.operationResult).toBe(operationResult)
    expect(result?.slot).toBeDefined()
  })

  it('undo を取消可能なイベントとして生成しない', async () => {
    const queue = await openTestQueue()
    const event: SyncEvent = {
      fields: { [STATE_DIFF_SLOT_ID]: 'source-state-diff' },
    }

    const result = await queueUndoEvent(
      request(queue, { game: 'game', d4: 'generation' }, event),
      {
        resolveUndoOperation: () => ({
          targetReference: targetReference('game', 'generation', 1),
          operationResult: {},
        }),
      },
    )

    expect(isCancellableEventKind(UNDO_EVENT_KIND)).toBe(false)
    expect(result?.slot?.event.fields).not.toHaveProperty(STATE_DIFF_SLOT_ID)
  })

  it('キュー状態・状況巻き戻し・履歴スタック・サーバー側分類を実装しない', () => {
    expect(undoQueueingSource).not.toMatch(/未送信|同期済み/)
    expect(undoQueueingSource).not.toMatch(
      /queueStateId|readSlot|countUnsentSlots|historyStack|nextUndoTarget|previousState/,
    )
    expect(undoQueueingSource).not.toMatch(
      /savedResult|sameRequest|continuousPrefix|gapClassification/,
    )
    expect(undoQueueingSource).not.toMatch(
      /operationResult\s*(?:===|!==)|switch\s*\(\s*operationResult/,
    )
    expect(undoQueueingSource).not.toMatch(/(['"])(?:V(?:[1-9]|1[0-2]))\1/)
    expect(undoQueueingSource).not.toMatch(/(['"])(?:[1-9]|1[0-2])\1/)
    expect(queueUndoEvent).toBeTypeOf('function')
  })
})

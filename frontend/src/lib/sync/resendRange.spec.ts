import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import ackAdapterSource from './ackAdapter.ts?raw'
import { createAckAdapterInjections } from './ackAdapter'
import { parseD1AckEnvelope } from './ackEnvelope'
import { ACK_BOUNDARY_RESULTS } from './boundaryResults'
import {
  CANON_ACK_STATE_RESULT,
  readCanonAckStateResults,
  type CanonAckStateResult,
} from './canonOracle'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
  type DurableQueueSlot,
} from './durableQueue'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
import { EVENT_KIND_RULES } from './eventKinds'
import queueTransitionSource from './queueTransition.ts?raw'
import { queueStateId, type QueueStateId } from './queueState'
import resendRangeSource from './resendRange.ts?raw'
import {
  determineResendRange,
  type D1AfterD3Resolver,
  type ResendD3Checkpoint,
  type ResendRangeRequest,
} from './resendRange'
import type { SyncEvent } from './syncEvent'

const CURRENT_D4 = 'current-generation'
const OTHER_D4 = 'other-generation'
const UNSENT_STATE = queueStateId('未送信')
const SYNCED_STATE = queueStateId('同期済み')
const ACK_RESULTS = readCanonAckStateResults()
const ACCEPTED_ACK_RESULT = ackResultById(CANON_ACK_STATE_RESULT.ACCEPTED)
const DUPLICATE_ACK_RESULT = ackResultById(CANON_ACK_STATE_RESULT.DUPLICATE)
const B1_BOUNDARY_RESULT = ACK_BOUNDARY_RESULTS.find(
  (result) => result.boundaryResult.id === 'B1',
)
if (!B1_BOUNDARY_RESULT) {
  throw new Error('B1 境界結果がありません')
}
const B1_BOUNDARY_RESULT_ID = B1_BOUNDARY_RESULT.boundaryResult.id
const NON_PLAYER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name !== '選手のその場登録',
)
if (!NON_PLAYER_EVENT_KIND) {
  throw new Error('再送検査用のイベント種別がありません')
}
const EVENT: SyncEvent = {
  fields: { [EVENT_KIND_SLOT_ID]: NON_PLAYER_EVENT_KIND.id },
}

let databaseSequence = 0
const openedQueues: DurableQueue[] = []
const databaseNames: string[] = []

function ackResultById(id: string): CanonAckStateResult {
  const result = ACK_RESULTS.find((candidate) => candidate.id === id)
  if (!result) {
    throw new Error(`A5 結果がありません: ${id}`)
  }
  return result
}

function slot(
  d1: number,
  state: QueueStateId = UNSENT_STATE,
  d4: unknown = CURRENT_D4,
): DurableQueueSlot {
  return {
    game: 'game',
    d4,
    d1,
    d5: `d5-${d1}`,
    version: `version-${d1}`,
    event: EVENT,
    state,
  }
}

const isD1AfterD3: D1AfterD3Resolver = (d1, d3) => d1 > (d3 as number)

function checkpoint(d3: unknown): ResendD3Checkpoint {
  return { d4: CURRENT_D4, d3 }
}

async function openTestQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const databaseName = `resend-range-${databaseSequence}`
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => false,
  })
  databaseNames.push(databaseName)
  openedQueues.push(queue)
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

async function appendRange(
  queue: DurableQueue,
  scope: DurableQueueScope,
): Promise<readonly DurableQueueSlot[]> {
  const first = await queue.append(
    queue.prepareAppend({
      scope,
      d5: 'first-d5',
      version: 'first-version',
      event: EVENT,
    }),
  )
  const second = await queue.append(
    queue.prepareAppend({
      scope,
      d5: 'second-d5',
      version: 'second-version',
      event: EVENT,
    }),
  )
  return [first, second]
}

function ackCandidate(
  slots: readonly DurableQueueSlot[],
  result: CanonAckStateResult,
  advancedD3: unknown,
): unknown {
  return {
    advancedD3,
    eventResults: slots.map((candidate) => ({
      d4: candidate.d4,
      d1: candidate.d1,
      d5: candidate.d5,
      a5Result: result.id,
    })),
  }
}

async function persistAckResults(
  queue: DurableQueue,
  scope: DurableQueueScope,
  slots: readonly DurableQueueSlot[],
  envelope: unknown,
): Promise<void> {
  const injections = createAckAdapterInjections({
    d1: {
      envelope,
      boundaryResult: B1_BOUNDARY_RESULT_ID,
    },
  })
  for (const candidate of slots) {
    const preparation = await queue.prepareA5Transition(
      scope,
      candidate.d1,
      injections,
    )
    if (!preparation) {
      throw new Error('A5 永続遷移の preparation がありません')
    }
    await queue.persistA5Transition(preparation)
  }
}

async function statesOf(
  queue: DurableQueue,
  scope: DurableQueueScope,
  slots: readonly DurableQueueSlot[],
): Promise<readonly QueueStateId[]> {
  return Promise.all(
    slots.map(async (candidate) => {
      const stored = await queue.readSlot(scope, candidate.d1)
      if (!stored) {
        throw new Error('再送検査対象のスロットがありません')
      }
      return stored.state
    }),
  )
}

afterEach(async () => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  for (const name of databaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

describe('resendRange', () => {
  it('同じ D4 の未送信スロットから既知 D3 より後だけを選ぶ', () => {
    const before = slot(1)
    const first = slot(2)
    const alreadySynced = slot(3, SYNCED_STATE)
    const last = slot(4)
    const otherGeneration = slot(5, UNSENT_STATE, OTHER_D4)

    const result = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: [before, first, alreadySynced, last, otherGeneration],
      lastKnownSynced: checkpoint(1),
      isD1AfterD3,
    })

    expect(result).toEqual({
      status: 'ready',
      checkpoint: checkpoint(1),
      slots: [first, last],
    })
    expect(Object.isFrozen(result.slots)).toBe(true)
  })

  it('ACK の D3 を直前の記憶より優先して次の再送範囲に使う', () => {
    const d3 = Symbol('advanced D3')
    const comparison = vi.fn<D1AfterD3Resolver>((d1, candidateD3) =>
      Object.is(candidateD3, d3) ? d1 > 2 : undefined,
    )
    const ack = parseD1AckEnvelope({ advancedD3: d3, eventResults: [] })

    const result = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: [slot(1), slot(2), slot(3)],
      lastKnownSynced: checkpoint(0),
      ack,
      isD1AfterD3: comparison,
    })

    expect(result).toEqual({
      status: 'ready',
      checkpoint: checkpoint(d3),
      slots: [slot(3)],
    })
    expect(comparison).toHaveBeenCalledTimes(3)
    expect(
      comparison.mock.calls.every(([, value]) => Object.is(value, d3)),
    ).toBe(true)
  })

  it('未送信が無いときは解決済みの空範囲を返す', () => {
    const comparison = vi.fn<D1AfterD3Resolver>(() => true)

    const result = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: [slot(1, SYNCED_STATE), slot(2, SYNCED_STATE)],
      lastKnownSynced: checkpoint(2),
      isD1AfterD3: comparison,
    })

    expect(result).toEqual({
      status: 'ready',
      checkpoint: checkpoint(2),
      slots: [],
    })
    expect(comparison).not.toHaveBeenCalled()
  })

  it('ACK 未受領かつ既知 D3 が無いと空範囲で fail-closed にする', () => {
    const comparison = vi.fn<D1AfterD3Resolver>(() => true)

    const result = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      isD1AfterD3: comparison,
    })

    expect(result).toEqual({
      status: 'unavailable',
      reason: 'd3-unknown',
      slots: [],
    })
    expect(comparison).not.toHaveBeenCalled()
  })

  it('別 D4 の既知 D3 を現在世代へ流用せず fail-closed にする', () => {
    const comparison = vi.fn<D1AfterD3Resolver>(() => true)

    const result = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      lastKnownSynced: { d4: OTHER_D4, d3: 0 },
      isD1AfterD3: comparison,
    })

    expect(result).toEqual({
      status: 'unavailable',
      reason: 'd4-mismatch',
      slots: [],
    })
    expect(comparison).not.toHaveBeenCalled()
  })

  it.each([
    {
      d4: undefined,
      orderedSlots: [slot(1)],
      lastKnownSynced: checkpoint(0),
      isD1AfterD3,
    },
    {
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      lastKnownSynced: { d4: CURRENT_D4, d3: undefined },
      isD1AfterD3,
    },
    {
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      ack: { advancedD3: undefined, eventResults: [] },
      isD1AfterD3,
    },
  ] as const)('D4 または D3 が undefined の入力を拒否する', (request) => {
    expect(() => determineResendRange(request as ResendRangeRequest)).toThrow()
  })

  it.each([
    {
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      lastKnownSynced: checkpoint(0),
      isD1AfterD3,
      extra: {},
    },
    {
      d4: CURRENT_D4,
      orderedSlots: [slot(1)],
      lastKnownSynced: { ...checkpoint(0), extra: {} },
      isD1AfterD3,
    },
    {
      d4: CURRENT_D4,
      orderedSlots: [{ ...slot(1), extra: {} }],
      lastKnownSynced: checkpoint(0),
      isD1AfterD3,
    },
  ])('余分なキーを持つ再送入力を拒否する', (request) => {
    expect(() => determineResendRange(request as ResendRangeRequest)).toThrow()
  })

  it('orderedSlots の同じ D4・D1 を重複として拒否する', () => {
    const first = slot(1)

    expect(() =>
      determineResendRange({
        d4: CURRENT_D4,
        orderedSlots: [first, { ...first }],
        lastKnownSynced: checkpoint(0),
        isD1AfterD3,
      }),
    ).toThrowError(/重複/)
  })

  it.each([null, 0, 'true', {}])(
    'resolver の非 boolean 戻り値 %j を order-unknown として拒否する',
    (resolverResult) => {
      const resolver = (() => resolverResult) as unknown as D1AfterD3Resolver

      expect(
        determineResendRange({
          d4: CURRENT_D4,
          orderedSlots: [slot(1)],
          lastKnownSynced: checkpoint(0),
          isD1AfterD3: resolver,
        }),
      ).toEqual({
        status: 'unavailable',
        reason: 'order-unknown',
        slots: [],
      })
    },
  )

  it.each([
    ['不明', (): boolean | undefined => undefined],
    [
      '例外',
      (): boolean | undefined => {
        throw new Error('比較不能')
      },
    ],
  ] as const)(
    'D1・D3 の順序が%sなら空範囲で fail-closed にする',
    (_name, compare) => {
      expect(
        determineResendRange({
          d4: CURRENT_D4,
          orderedSlots: [slot(1)],
          lastKnownSynced: checkpoint(0),
          isD1AfterD3: compare,
        }),
      ).toEqual({
        status: 'unavailable',
        reason: 'order-unknown',
        slots: [],
      })
    },
  )

  it('ACK 消失後に同じ範囲を再送しても最終状態が変わらない', async () => {
    const immediateQueue = await openTestQueue()
    const retryQueue = await openTestQueue()
    const scope: DurableQueueScope = { game: 'game', d4: CURRENT_D4 }
    const immediateSlots = await appendRange(immediateQueue, scope)
    const retrySlots = await appendRange(retryQueue, scope)
    const initialCheckpoint = checkpoint(0)
    const initialRetryRange = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: retrySlots,
      lastKnownSynced: initialCheckpoint,
      isD1AfterD3,
    })
    const lostAckRetryRange = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: retrySlots,
      lastKnownSynced: initialCheckpoint,
      isD1AfterD3,
    })

    expect(initialRetryRange.status).toBe('ready')
    expect(lostAckRetryRange.status).toBe('ready')
    expect(initialRetryRange.slots.map((candidate) => candidate.d1)).toEqual(
      lostAckRetryRange.slots.map((candidate) => candidate.d1),
    )

    const immediateAck = ackCandidate(
      immediateSlots,
      ACCEPTED_ACK_RESULT,
      immediateSlots.at(-1)?.d1,
    )
    const replayedAck = ackCandidate(
      retrySlots,
      DUPLICATE_ACK_RESULT,
      retrySlots.at(-1)?.d1,
    )
    await persistAckResults(immediateQueue, scope, immediateSlots, immediateAck)
    await persistAckResults(retryQueue, scope, retrySlots, replayedAck)

    expect(await statesOf(retryQueue, scope, retrySlots)).toEqual(
      await statesOf(immediateQueue, scope, immediateSlots),
    )
    expect(await statesOf(retryQueue, scope, retrySlots)).toEqual([
      SYNCED_STATE,
      SYNCED_STATE,
    ])

    const persistedRetrySlots = await Promise.all(
      retrySlots.map((candidate) => retryQueue.readSlot(scope, candidate.d1)),
    )
    const nextRange = determineResendRange({
      d4: CURRENT_D4,
      orderedSlots: persistedRetrySlots.filter(
        (candidate): candidate is DurableQueueSlot => candidate !== undefined,
      ),
      lastKnownSynced: initialCheckpoint,
      ack: parseD1AckEnvelope(replayedAck),
      isD1AfterD3,
    })
    expect(nextRange.status).toBe('ready')
    expect(nextRange.slots).toEqual([])
  })

  it('D3 を変えても同じ A5 による状態遷移結果は変わらない', async () => {
    const firstQueue = await openTestQueue()
    const secondQueue = await openTestQueue()
    const scope: DurableQueueScope = { game: 'd3-game', d4: CURRENT_D4 }
    const firstSlots = await appendRange(firstQueue, scope)
    const secondSlots = await appendRange(secondQueue, scope)
    const firstAck = ackCandidate(firstSlots, ACCEPTED_ACK_RESULT, -1)
    const secondAck = ackCandidate(secondSlots, ACCEPTED_ACK_RESULT, 999)

    await persistAckResults(firstQueue, scope, firstSlots, firstAck)
    await persistAckResults(secondQueue, scope, secondSlots, secondAck)

    expect(await statesOf(firstQueue, scope, firstSlots)).toEqual(
      await statesOf(secondQueue, scope, secondSlots),
    )
  })

  it('D3 の参照を再送範囲へ閉じ、遷移規則とサーバー側処理を持たない', () => {
    expect(resendRangeSource).toContain('request.ack.advancedD3')
    expect(resendRangeSource).not.toMatch(
      /evaluateQueueTransition|QueueTransition|a5Result|\.d5\b/,
    )
    expect(resendRangeSource).not.toMatch(
      /savedResult|replayedResult|idempotency|authorization|V12/i,
    )
    expect(queueTransitionSource).not.toMatch(/\bD3\b|advancedD3/)
    expect(ackAdapterSource).not.toContain('advancedD3')
    expect(resendRangeSource).not.toMatch(/(['"])(?:V(?:[1-9]|1[0-2]))\1/)
    expect(resendRangeSource).not.toMatch(/(['"])(?:[1-9]|1[0-2])\1/)
    expect(resendRangeSource).not.toMatch(
      /\.match\s*\(|\.test\s*\(|\bRegExp\b|charCodeAt|codePointAt|UUID/i,
    )
  })
})

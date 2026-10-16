import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it } from 'vitest'
import { NO_ACK_BOUNDARY_RESULTS } from '../lib/sync/boundaryResults'
import { CANON_ACK_STATE_RESULT } from '../lib/sync/canonOracle'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'
import { B3_REJECTION_KIND } from '../lib/sync/rejectionReason'
import type { SyncEvent } from '../lib/sync/syncEvent'
import {
  ACK_APPLICATION_REASON,
  applyAckToSlot,
  type AckResponse,
} from './GameScreenAckApplication'
import ackApplicationSource from './GameScreenAckApplication.ts?raw'

const gameId = 'f1e2d3c4-b5a6-4789-9abc-def012345678'
const d4 = 'generation-a'
const d5 = '0b5f1c2e-3a4d-4e5f-8a9b-0c1d2e3f4a5b'
const scope: DurableQueueScope = { game: gameId, d4 }

let databaseSequence = 0
const openedQueues: DurableQueue[] = []

afterEach(() => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
})

async function openIsolatedQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const queue = await openDurableQueue({
    databaseName: `uf8-ack-application-${databaseSequence}`,
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

async function appendPitch(queue: DurableQueue): Promise<DurableQueueSlot> {
  return queue.append(
    queue.prepareAppend({ scope, d5, version: {}, event: pitchEvent() }),
  )
}

function ackFor(
  slot: DurableQueueSlot,
  a5Result: string,
  overrides: Partial<AckResponse> = {},
): AckResponse {
  return {
    envelope: {
      advancedD3: 0,
      eventResults: [{ d4: slot.d4, d1: slot.d1, d5: slot.d5, a5Result }],
    },
    boundaryResult: 'B1',
    ...overrides,
  }
}

describe('ACK を既存スロットへ適用する', () => {
  it('受理の ACK で同期済みへ遷移する', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.ACCEPTED),
      },
      queue,
    )

    expect(result.outcome).toBe('applied')
    if (result.outcome !== 'applied') return
    expect(result.slot.state).toBe(queueStateId('同期済み'))
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('同期済み'),
    )
  })

  it('B3 を含む ACK の拒否で要操作へ遷移する', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.REJECTED, {
          boundaryResult: 'B3',
          b3Rejection: {
            kind: B3_REJECTION_KIND.O4,
            reason: 'opaque-reason',
          },
        }),
      },
      queue,
    )

    expect(result.outcome).toBe('applied')
    if (result.outcome !== 'applied') return
    expect(result.slot.state).toBe(queueStateId('要操作'))
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('要操作'),
    )
  })

  it('未処理の ACK では未送信のまま残る', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.UNPROCESSED),
      },
      queue,
    )

    expect(result.outcome).toBe('applied')
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
    expect(await queue.countUnsentSlots()).toBe(1)
  })
})

describe('ACK が返らないときは未送信のまま', () => {
  it('ACK を渡さなければ何も変えない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot({ scope, d1: slot.d1 }, queue)

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NO_ACK_RECEIVED,
    })
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
  })

  it('ACK が返らない境界結果では何も変えない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)
    const noAckBoundaryResult = NO_ACK_BOUNDARY_RESULTS[0]
    expect(noAckBoundaryResult).toBeDefined()

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.ACCEPTED, {
          boundaryResult: noAckBoundaryResult!.boundaryResult.id,
        }),
      },
      queue,
    )

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.ACK_NOT_INTERPRETABLE,
    })
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
  })

  it('未知の境界結果では何も変えない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.ACCEPTED, {
          boundaryResult: 'B999',
        }),
      },
      queue,
    )

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.ACK_NOT_INTERPRETABLE,
    })
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
  })

  it('読めない封筒では何も変えない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: { envelope: { broken: true }, boundaryResult: 'B1' },
      },
      queue,
    )

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.ACK_NOT_INTERPRETABLE,
    })
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
  })
})

describe('適用できない対象', () => {
  it('対象のスロットが無ければ適用しない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1 + 1,
        ack: ackFor(slot, CANON_ACK_STATE_RESULT.ACCEPTED),
      },
      queue,
    )

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NO_TARGET_SLOT,
    })
  })

  it('別のイベントの ACK では遷移しない', async () => {
    const queue = await openIsolatedQueue()
    const slot = await appendPitch(queue)
    const foreign: DurableQueueSlot = { ...slot, d5: 'other-d5' }

    const result = await applyAckToSlot(
      {
        scope,
        d1: slot.d1,
        ack: ackFor(foreign, CANON_ACK_STATE_RESULT.ACCEPTED),
      },
      queue,
    )

    expect(result).toEqual({
      outcome: 'not-applied',
      reason: ACK_APPLICATION_REASON.NOT_TRANSITIONED,
    })
    expect((await queue.readSlot(scope, slot.d1))?.state).toBe(
      queueStateId('未送信'),
    )
  })
})

describe('分類と遷移を再実装しない', () => {
  it('ACK の読み取りと遷移を既存の成果へ委ねている', () => {
    expect(ackApplicationSource).toContain('createAckAdapterInjections(')
    expect(ackApplicationSource).toContain('prepareA5Transition(')
    expect(ackApplicationSource).toContain('persistA5Transition(')
  })

  it('境界結果・A5 の語・遷移表を本モジュールのコードで持たない', () => {
    // 典拠を示す注釈は正本の語を引く。検査するのはコードだけ。
    const code = ackApplicationSource
      .split(/\r\n?|\n/)
      .map((line) => line.replace(/\/\/.*$/, ''))
      .join('\n')

    expect(code).not.toMatch(/\bB[0-9]+\b/)
    expect(code).not.toMatch(/受理|重複|拒否|退避|未処理|同期済み|要操作/)
    expect(code).not.toContain('evaluateQueueTransition')
    expect(code).not.toContain('QUEUE_TRANSITION')
  })
})

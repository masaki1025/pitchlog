import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it } from 'vitest'
import ackAdapterSource from './ackAdapter.ts?raw'
import { createAckAdapterInjections } from './ackAdapter'
import { ACK_BOUNDARY_RESULTS } from './boundaryResults'
import {
  CANON_ACK_STATE_RESULT,
  readCanonAckStateResults,
  readCanonP3BoundaryResults,
  type CanonAckStateResult,
  type CanonP3BoundaryResult,
} from './canonOracle'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueScope,
  type DurableQueueSlot,
} from './durableQueue'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import { B3_CONTENT_BRANCH, B3_REJECTION_KIND } from './rejectionReason'
import {
  actionRequiredLabelId,
  queueStateId,
  type I6Acceptance,
} from './queueState'
import { evaluateQueueTransition, type QueueEventKey } from './queueTransition'
import {
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'

type AcceptedP3BoundaryResult = Extract<
  CanonP3BoundaryResult,
  { accepted: true }
>

const ACK_RESULTS = readCanonAckStateResults()
const ACCEPTED_ACK_RESULT = ackResultById(CANON_ACK_STATE_RESULT.ACCEPTED)
const REJECTED_ACK_RESULT = ackResultById(CANON_ACK_STATE_RESULT.REJECTED)
const B3_BOUNDARY_RESULT = ackBoundaryResultById('B3')
const B1_BOUNDARY_RESULT = ackBoundaryResultById('B1')
const ACCEPTED_P3_BOUNDARY_RESULT = acceptedP3BoundaryResult()
const PLAYER_REGISTRATION_EVENT_KIND = eventKindByName('選手のその場登録')
const OTHER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.id !== PLAYER_REGISTRATION_EVENT_KIND.id,
)
if (!OTHER_EVENT_KIND) {
  throw new Error('アダプタ検査用のイベント種別がありません')
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

function ackBoundaryResultById(id: string) {
  const result = ACK_BOUNDARY_RESULTS.find(
    (candidate) => candidate.boundaryResult.id === id,
  )
  if (!result) {
    throw new Error(`ACK 境界結果がありません: ${id}`)
  }
  return result.boundaryResult
}

function acceptedP3BoundaryResult(): AcceptedP3BoundaryResult {
  const result = readCanonP3BoundaryResults().find(
    (candidate): candidate is AcceptedP3BoundaryResult => candidate.accepted,
  )
  if (!result) {
    throw new Error('P3 変更受理結果がありません')
  }
  return result
}

function eventKindByName(name: string): EventKind {
  const eventKind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === name,
  )
  if (!eventKind) {
    throw new Error(`イベント種別がありません: ${name}`)
  }
  return eventKind
}

function eventOfKind(eventKind: EventKind): SyncEvent {
  return { fields: { [EVENT_KIND_SLOT_ID]: eventKind.id } }
}

function eventKey(slot: DurableQueueSlot): QueueEventKey {
  return { d4: slot.d4, d1: slot.d1, d5: slot.d5 }
}

function targetReference(): TargetEventReference {
  return Object.fromEntries(
    TARGET_EVENT_REFERENCE_ELEMENTS.map((element, index) => [
      element,
      `target-${index}`,
    ]),
  ) as TargetEventReference
}

function p3Acceptance(): I6Acceptance {
  return {
    targetReference: targetReference(),
    expectedVersion: 'expected-version',
    d5: 'p3-d5',
    confirmedContent: 'confirmed-content',
  }
}

async function openTestQueue(): Promise<DurableQueue> {
  databaseSequence += 1
  const databaseName = `ack-adapter-${databaseSequence}`
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

afterEach(async () => {
  for (const queue of openedQueues.splice(0)) {
    queue.close()
  }
  for (const name of databaseNames.splice(0)) {
    await deleteDatabase(name)
  }
})

describe('ackAdapter', () => {
  it('D1 と P3 から4点を供給し、既存の遷移判定を成立させる', async () => {
    const queue = await openTestQueue()
    const scope: DurableQueueScope = { game: 'game', d4: 'generation' }
    const temporaryId = 'temporary-player'
    const officialId = 'official-player'
    const playerSlot = await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'player-d5',
        version: 'player-version',
        event: eventOfKind(PLAYER_REGISTRATION_EVENT_KIND),
      }),
    )
    const rejectedSlot = await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'rejected-d5',
        version: 'rejected-version',
        event: eventOfKind(OTHER_EVENT_KIND),
      }),
    )
    const expectedP3 = p3Acceptance()
    const acceptedAt = 'server-accepted-at'
    const injections = createAckAdapterInjections({
      d1: {
        envelope: {
          advancedD3: playerSlot.d1,
          eventResults: [
            {
              ...eventKey(playerSlot),
              a5Result: ACCEPTED_ACK_RESULT.id,
            },
            {
              ...eventKey(rejectedSlot),
              a5Result: REJECTED_ACK_RESULT.id,
            },
          ],
          playerIdMappings: [{ temporaryId, officialId }],
        },
        boundaryResult: B3_BOUNDARY_RESULT.id,
        b3Rejection: {
          kind: B3_REJECTION_KIND.CONTENT,
          branch: B3_CONTENT_BRANCH.B3A,
          reason: '入力内容を確認してください',
        },
        playerIdMappingTarget: {
          eventKind: PLAYER_REGISTRATION_EVENT_KIND,
          event: playerSlot.event,
          key: eventKey(playerSlot),
          temporaryId,
        },
      },
      p3: {
        envelope: {
          boundaryResult: ACCEPTED_P3_BOUNDARY_RESULT.id,
          acceptedResult: { ...expectedP3, acceptedAt },
        },
        expected: expectedP3,
      },
    })

    expect(Reflect.ownKeys(injections).sort()).toEqual(
      [
        'resolveA5',
        'classifyB3',
        'resolvePlayerRegistrationMapping',
        'resolveAcceptedAt',
      ].sort(),
    )

    const playerPreparation = await queue.prepareA5Transition(
      scope,
      playerSlot.d1,
      injections,
    )
    if (!playerPreparation) {
      throw new Error('選手登録イベントの A5 preparation がありません')
    }
    const playerTransition = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        queue,
        preparation: playerPreparation,
      },
      injections,
    )
    expect(playerTransition).toMatchObject({
      applied: true,
      target: queueStateId('同期済み'),
    })

    const rejectedPreparation = await queue.prepareA5Transition(
      scope,
      rejectedSlot.d1,
      injections,
    )
    if (!rejectedPreparation) {
      throw new Error('拒否イベントの A5 preparation がありません')
    }
    const rejectedTransition = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        queue,
        preparation: rejectedPreparation,
      },
      injections,
    )
    expect(rejectedTransition).toMatchObject({
      applied: true,
      target: queueStateId('要操作'),
    })
    expect(
      rejectedTransition.applied &&
        rejectedTransition.slot?.source === 'd1-event'
        ? rejectedTransition.slot.actionRequiredLabel
        : undefined,
    ).toBeUndefined()

    const p3Preparation = queue.prepareI6Acceptance(expectedP3, injections)
    if (!p3Preparation) {
      throw new Error('P3 受理結果の I6 preparation がありません')
    }
    const persistenceReceipt = await queue.persistI6Acceptance(p3Preparation)
    const p3Transition = evaluateQueueTransition({
      kind: 'p3-acceptance-persisted',
      persistenceReceipt,
    })
    expect(p3Transition).toMatchObject({
      applied: true,
      target: queueStateId('同期済み'),
      slot: { acceptedAt },
    })
  })

  it('O4 の分類だけを供給し、是正済み確認は供給しない', async () => {
    const queue = await openTestQueue()
    const scope: DurableQueueScope = { game: 'o4-game', d4: 'o4-generation' }
    const slot = await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'o4-d5',
        version: 'o4-version',
        event: eventOfKind(OTHER_EVENT_KIND),
      }),
    )
    const injections = createAckAdapterInjections({
      d1: {
        envelope: {
          advancedD3: 0,
          eventResults: [
            { ...eventKey(slot), a5Result: REJECTED_ACK_RESULT.id },
          ],
        },
        boundaryResult: B3_BOUNDARY_RESULT.id,
        b3Rejection: {
          kind: B3_REJECTION_KIND.O4,
          reason: 'opaque-reason',
        },
      },
    })
    const preparation = await queue.prepareA5Transition(
      scope,
      slot.d1,
      injections,
    )
    if (!preparation) {
      throw new Error('O4 イベントの A5 preparation がありません')
    }

    const transition = evaluateQueueTransition(
      { kind: 'apply-a5', queue, preparation },
      injections,
    )

    expect(transition).toMatchObject({
      applied: true,
      target: queueStateId('要操作'),
      slot: {
        actionRequiredLabel: actionRequiredLabelId('管理者対応待ち'),
      },
    })
    expect(Object.hasOwn(injections, 'confirmO4Correction')).toBe(false)
  })

  it('応答が無いと4点をすべて未注入のままにして遷移しない', async () => {
    const queue = await openTestQueue()
    const scope: DurableQueueScope = {
      game: 'no-response-game',
      d4: 'no-response-generation',
    }
    const slot = await queue.append(
      queue.prepareAppend({
        scope,
        d5: 'no-response-d5',
        version: 'no-response-version',
        event: eventOfKind(PLAYER_REGISTRATION_EVENT_KIND),
      }),
    )
    const injections = createAckAdapterInjections()

    expect(Reflect.ownKeys(injections)).toEqual([])
    expect(injections.resolveA5).toBeUndefined()
    expect(injections.classifyB3).toBeUndefined()
    expect(injections.resolvePlayerRegistrationMapping).toBeUndefined()
    expect(injections.resolveAcceptedAt).toBeUndefined()

    const preparation = await queue.prepareA5Transition(
      scope,
      slot.d1,
      injections,
    )
    if (!preparation) {
      throw new Error('未応答検査用の A5 preparation がありません')
    }
    expect(
      evaluateQueueTransition(
        { kind: 'apply-a5', queue, preparation },
        injections,
      ),
    ).toEqual({ applied: false })
    expect(
      queue.prepareI6Acceptance(p3Acceptance(), injections),
    ).toBeUndefined()
  })

  it('既存の5成果だけを呼び、遷移・判定・写像を再実装しない', () => {
    for (const calledFunction of [
      'parseD1AckEnvelope',
      'parseAckBoundaryResult',
      'parseB3Rejection',
      'receivePlayerIdMapping',
      'parseP3ResultEnvelope',
    ]) {
      expect(ackAdapterSource).toMatch(
        new RegExp(`\\b${calledFunction}\\s*\\(`),
      )
    }

    expect(ackAdapterSource).not.toMatch(
      /QUEUE_TRANSITION_(?:RULES|ROW_IDS)|CANON_ACK_STATE_RESULT/,
    )
    expect(ackAdapterSource).not.toMatch(
      /\b(?:new\s+(?:Map|Set|TemporaryIdMapping)|switch\s*\()/,
    )
    expect(ackAdapterSource).not.toMatch(/改訂待ち|墓標待ち/)
    expect(ackAdapterSource).not.toMatch(/(['"])(?:V(?:[1-9]|1[0-2]))\1/)
    expect(ackAdapterSource).not.toMatch(/(['"])(?:[1-9]|1[0-2])\1/)
    expect(ackAdapterSource).not.toMatch(
      /\.match\s*\(|\.test\s*\(|\bRegExp\b|charCodeAt|codePointAt|UUID/i,
    )
  })

  // 写像確認の注入を別イベントへ使い回せないことを、キーの 3 要素それぞれで固定する。
  // これが無いと「引数を無視して常に写像を返す」実装でもテストが通る(差分レビュー P1)。
  it.each([
    ['D4', { d4: 'other-generation' }],
    ['D1', { d1: 999 }],
    ['D5', { d5: 'other-d5' }],
  ])('A4 の注入は %s が異なるキーへ使い回せない', (_name, override) => {
    const targetKey: QueueEventKey = {
      d4: 'generation-a',
      d1: 1,
      d5: 'd5-a',
    }
    const event = eventOfKind(PLAYER_REGISTRATION_EVENT_KIND)
    const injections = createAckAdapterInjections({
      d1: {
        envelope: {
          advancedD3: targetKey.d1,
          eventResults: [{ ...targetKey, a5Result: ACCEPTED_ACK_RESULT.id }],
          playerIdMappings: [
            { temporaryId: 'temporary-player', officialId: 'official-player' },
          ],
        },
        boundaryResult: B1_BOUNDARY_RESULT.id,
        playerIdMappingTarget: {
          eventKind: PLAYER_REGISTRATION_EVENT_KIND,
          event,
          key: targetKey,
          temporaryId: 'temporary-player',
        },
      },
    })
    const resolver = injections.resolvePlayerRegistrationMapping
    if (!resolver) {
      throw new Error('写像確認の注入がありません')
    }

    expect(resolver({ key: targetKey, event })).toBe(true)
    expect(resolver({ key: { ...targetKey, ...override }, event })).toBe(
      undefined,
    )
  })
})

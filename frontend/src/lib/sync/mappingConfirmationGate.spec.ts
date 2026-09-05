import 'fake-indexeddb/auto'

import { afterEach, describe, expect, it, vi } from 'vitest'
import mappingConfirmationGateSource from './mappingConfirmationGate.ts?raw'
import {
  readCanonAckStateResults,
  readCanonTemporaryIdMappingRules,
} from './canonOracle'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueuePreparation,
} from './durableQueue'
import {
  C4_MAPPING_CONFIRMATION_RULE,
  checkMappingConfirmation,
  MAPPING_CONFIRMATION_STATUS,
  type MappingConfirmationInjections,
  type PlayerRegistrationMappingResolver,
} from './mappingConfirmationGate'
import { queueStateId } from './queueState'
import {
  evaluateQueueTransition,
  queueTransitionRuleById,
  type QueueSlot,
  type QueueTransitionInjections,
  type QueueTransitionRequest,
} from './queueTransition'

const PLAYER_REGISTRATION_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name === '選手のその場登録',
)
const OTHER_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.id !== PLAYER_REGISTRATION_EVENT_KIND?.id,
)
if (!PLAYER_REGISTRATION_EVENT_KIND || !OTHER_EVENT_KIND) {
  throw new Error('ゲート検査用のイベント種別がありません')
}

function eventFor(eventKind: EventKind) {
  return { fields: { [EVENT_KIND_SLOT_ID]: eventKind.id } }
}
const BASE_EVENT = eventFor(PLAYER_REGISTRATION_EVENT_KIND)
let databaseSequence = 0
const openedQueues: DurableQueue[] = []
const databaseNames: string[] = []

function deleteDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('テスト DB を削除できません'))
  })
}

async function storedA5Preparation(
  eventKind: EventKind,
  mappingInjections: MappingConfirmationInjections = {},
): Promise<{
  preparation: DurableQueuePreparation<'a5-transition'>
  slot: Extract<QueueSlot, { source: 'd1-event' }>
}> {
  databaseSequence += 1
  const databaseName = `mapping-confirmation-${databaseSequence}`
  databaseNames.push(databaseName)
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => false,
  })
  openedQueues.push(queue)
  const scope = {
    game: `game-${databaseSequence}`,
    d4: `generation-${databaseSequence}`,
  }
  const stored = await queue.append(
    queue.prepareAppend({
      scope,
      d5: `d5-${databaseSequence}`,
      version: {},
      event: eventFor(eventKind),
    }),
  )
  const preparation = await queue.prepareA5Transition(
    scope,
    stored.d1,
    mappingInjections,
  )
  if (!preparation) {
    throw new Error('A5 遷移 preparation がありません')
  }
  return {
    preparation,
    slot: {
      state: queueStateId('未送信'),
      source: 'd1-event',
      key: { d4: stored.d4, d1: stored.d1, d5: stored.d5 },
      content: stored.event,
    },
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

function syncedAckResult() {
  const syncedRule = queueTransitionRuleById('QT-02')
  if (!('a5ResultIds' in syncedRule.condition)) {
    throw new Error('同期済み遷移の A5 結果がありません')
  }
  const syncedA5ResultIds = new Set<string>(syncedRule.condition.a5ResultIds)
  const result = readCanonAckStateResults().find((candidate) =>
    syncedA5ResultIds.has(candidate.id),
  )
  if (!result) {
    throw new Error('同期済みへ移す A5 結果がありません')
  }
  return result
}

function syncedA5Injections(
  slot: Extract<QueueSlot, { source: 'd1-event' }>,
): QueueTransitionInjections {
  return {
    resolveA5: () => ({ key: slot.key, result: syncedAckResult() }),
  }
}

describe('mappingConfirmationGate', () => {
  it('C4 の右辺を R-TEMP-ID-MAPPING と逐語一致させる', () => {
    const canonRule = readCanonTemporaryIdMappingRules().find(
      (rule) => rule.id === C4_MAPPING_CONFIRMATION_RULE.id,
    )

    expect(canonRule).toBeDefined()
    expect(C4_MAPPING_CONFIRMATION_RULE).toEqual(canonRule)
  })

  const unconfirmedCases = [
    ['未注入', {}],
    ['false', { resolvePlayerRegistrationMapping: () => false }],
    ['undefined', { resolvePlayerRegistrationMapping: () => undefined }],
    [
      '例外',
      {
        resolvePlayerRegistrationMapping: () => {
          throw new Error('写像確認失敗')
        },
      },
    ],
  ] as const satisfies readonly (readonly [
    string,
    MappingConfirmationInjections,
  ])[]

  it.each(unconfirmedCases)(
    'A4 写像が%sなら未確定を返す',
    (_name, injections) => {
      const result = checkMappingConfirmation(
        {
          eventKind: PLAYER_REGISTRATION_EVENT_KIND,
          event: BASE_EVENT,
        },
        injections,
      )

      expect(result).toEqual({
        status: MAPPING_CONFIRMATION_STATUS.UNCONFIRMED,
        allowsSyncedTransition: false,
      })
    },
  )

  it('A4 写像が確定済みなら同期済み遷移を許可する', () => {
    const result = checkMappingConfirmation(
      { eventKind: PLAYER_REGISTRATION_EVENT_KIND, event: BASE_EVENT },
      { resolvePlayerRegistrationMapping: () => true },
    )

    expect(result).toEqual({
      status: MAPPING_CONFIRMATION_STATUS.CONFIRMED,
      allowsSyncedTransition: true,
    })
  })

  it('選手登録以外は resolver を呼ばず素通しする', () => {
    const resolver = vi.fn<PlayerRegistrationMappingResolver>(() => {
      throw new Error('呼び出してはいけません')
    })
    const result = checkMappingConfirmation(
      { eventKind: OTHER_EVENT_KIND, event: BASE_EVENT },
      { resolvePlayerRegistrationMapping: resolver },
    )

    expect(result).toEqual({
      status: MAPPING_CONFIRMATION_STATUS.NOT_REQUIRED,
      allowsSyncedTransition: true,
    })
    expect(resolver).not.toHaveBeenCalled()
  })

  it.each(unconfirmedCases)(
    '製品の A5 入口は選手登録の写像確認が%sなら D1 が prefix 内でも同期済みへ移さない',
    async (_name, mappingInjections) => {
      const { preparation, slot } = await storedA5Preparation(
        PLAYER_REGISTRATION_EVENT_KIND,
        mappingInjections,
      )
      const result = evaluateQueueTransition(
        {
          kind: 'apply-a5',
          preparation,
        },
        syncedA5Injections(slot),
      )

      expect(result.applied).toBe(false)
      expect(result.rowId).toBe('QT-02')
    },
  )

  it('製品の A5 入口は選手登録の写像確認が true のときだけ同期済みへ移す', async () => {
    const { preparation, slot } = await storedA5Preparation(
      PLAYER_REGISTRATION_EVENT_KIND,
      { resolvePlayerRegistrationMapping: () => true },
    )
    const result = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        preparation,
      },
      syncedA5Injections(slot),
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(queueStateId('同期済み'))
    }
  })

  it('製品の A5 入口は永続スロットが選手登録以外なら resolver なしで同期済みへ移す', async () => {
    const { preparation, slot } = await storedA5Preparation(OTHER_EVENT_KIND)
    const result = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        preparation,
      },
      syncedA5Injections(slot),
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(queueStateId('同期済み'))
    }
  })

  it('選手登録スロットへ別の既知種別を引数で渡しても C4 を迂回しない', async () => {
    const { preparation, slot } = await storedA5Preparation(
      PLAYER_REGISTRATION_EVENT_KIND,
    )
    const request = {
      kind: 'apply-a5',
      preparation,
      eventKind: OTHER_EVENT_KIND,
    } as unknown as QueueTransitionRequest

    expect(evaluateQueueTransition(request, syncedA5Injections(slot))).toEqual({
      applied: false,
      rowId: 'QT-02',
    })
  })

  it('永続スロットの種別だけで C4 を発火させる', async () => {
    const resolver = vi.fn(() => true)
    const { preparation, slot } = await storedA5Preparation(
      PLAYER_REGISTRATION_EVENT_KIND,
      { resolvePlayerRegistrationMapping: resolver },
    )

    expect(
      evaluateQueueTransition(
        { kind: 'apply-a5', preparation },
        syncedA5Injections(slot),
      ).applied,
    ).toBe(true)
    expect(resolver).toHaveBeenCalledWith(slot.content)
  })

  it('同じキーの平文スロットで V5 を改変しても同期済みにならない', async () => {
    const { preparation, slot } = await storedA5Preparation(
      PLAYER_REGISTRATION_EVENT_KIND,
    )
    const tamperedRequest = {
      kind: 'apply-a5',
      preparation,
      slot: { ...slot, content: eventFor(OTHER_EVENT_KIND) },
    } as unknown as QueueTransitionRequest

    expect(
      evaluateQueueTransition(tamperedRequest, syncedA5Injections(slot)),
    ).toEqual({ applied: false, rowId: 'QT-02' })
  })

  it('製品ファイルで D3 とイベント種別 ID の直書きをしない', () => {
    expect(mappingConfirmationGateSource).not.toContain('D3')
    expect(
      mappingConfirmationGateSource.match(/(['"`])(?:1[0-2]|[1-9])\1/g) ?? [],
    ).toHaveLength(0)
  })
})

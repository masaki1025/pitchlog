import { describe, expect, it, vi } from 'vitest'
import mappingConfirmationGateSource from './mappingConfirmationGate.ts?raw'
import {
  readCanonAckStateResults,
  readCanonTemporaryIdMappingRules,
} from './canonOracle'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
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
  type QueueEventKey,
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

const BASE_KEY: QueueEventKey = { d4: {}, d1: {}, d5: {} }
function eventFor(eventKind: EventKind) {
  return { fields: { [EVENT_KIND_SLOT_ID]: eventKind.id } }
}
const BASE_EVENT = eventFor(PLAYER_REGISTRATION_EVENT_KIND)

function unsentSlot(): Extract<QueueSlot, { source: 'd1-event' }> {
  return {
    state: queueStateId('未送信'),
    source: 'd1-event',
    key: BASE_KEY,
    content: BASE_EVENT,
  }
}

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
  mappingInjections: MappingConfirmationInjections = {},
): QueueTransitionInjections {
  return {
    resolveA5: () => ({ key: slot.key, result: syncedAckResult() }),
    ...mappingInjections,
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
    (_name, mappingInjections) => {
      const slot = { ...unsentSlot(), d3: BASE_KEY.d1 }
      const result = evaluateQueueTransition(
        {
          kind: 'apply-a5',
          slot,
        },
        syncedA5Injections(slot, mappingInjections),
      )

      expect(result.applied).toBe(false)
      expect(result.rowId).toBe('QT-02')
    },
  )

  it('製品の A5 入口は選手登録の写像確認が true のときだけ同期済みへ移す', () => {
    const slot = unsentSlot()
    const result = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        slot,
      },
      syncedA5Injections(slot, {
        resolvePlayerRegistrationMapping: () => true,
      }),
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(queueStateId('同期済み'))
    }
  })

  it('製品の A5 入口は選手登録以外を resolver なしで同期済みへ移す', () => {
    const slot = unsentSlot()
    const result = evaluateQueueTransition(
      {
        kind: 'apply-a5',
        slot: { ...slot, content: eventFor(OTHER_EVENT_KIND) },
      },
      syncedA5Injections(slot),
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(queueStateId('同期済み'))
    }
  })

  it('選手登録スロットへ別の既知種別を引数で渡しても C4 を迂回しない', () => {
    const slot = unsentSlot()
    const request = {
      kind: 'apply-a5',
      slot,
      eventKind: OTHER_EVENT_KIND,
    } as unknown as QueueTransitionRequest

    expect(evaluateQueueTransition(request, syncedA5Injections(slot))).toEqual({
      applied: false,
      rowId: 'QT-02',
    })
  })

  it('永続スロットの種別だけで C4 を発火させる', () => {
    const slot = unsentSlot()
    const resolver = vi.fn(() => true)

    expect(
      evaluateQueueTransition(
        { kind: 'apply-a5', slot },
        syncedA5Injections(slot, {
          resolvePlayerRegistrationMapping: resolver,
        }),
      ).applied,
    ).toBe(true)
    expect(resolver).toHaveBeenCalledWith(slot.content)
  })

  it('製品ファイルで D3 とイベント種別 ID の直書きをしない', () => {
    expect(mappingConfirmationGateSource).not.toContain('D3')
    expect(
      mappingConfirmationGateSource.match(/(['"`])(?:1[0-2]|[1-9])\1/g) ?? [],
    ).toHaveLength(0)
  })
})

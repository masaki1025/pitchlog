import { describe, expect, it, vi } from 'vitest'
import mappingConfirmationGateSource from './mappingConfirmationGate.ts?raw'
import {
  readCanonAckStateResults,
  readCanonTemporaryIdMappingRules,
} from './canonOracle'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
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
  type QueueTransitionResult,
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
const BASE_EVENT = {}

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

function evaluateAfterMappingConfirmation(
  slot: Extract<QueueSlot, { source: 'd1-event' }>,
  eventKind: EventKind,
  injections: MappingConfirmationInjections,
): QueueTransitionResult {
  const gateResult = checkMappingConfirmation(
    { eventKind, event: slot.content },
    injections,
  )
  if (!gateResult.allowsSyncedTransition) {
    return { applied: false }
  }

  return evaluateQueueTransition(
    { kind: 'apply-a5', slot },
    { resolveA5: () => ({ key: slot.key, result: syncedAckResult() }) },
  )
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

  it('写像未確定なら D1 が prefix 内でも同期済みへ移さない', () => {
    const slotWithPrefixEvidence = {
      ...unsentSlot(),
      d3: BASE_KEY.d1,
    }
    const result = evaluateAfterMappingConfirmation(
      slotWithPrefixEvidence,
      PLAYER_REGISTRATION_EVENT_KIND,
      {},
    )

    expect(result.applied).toBe(false)
  })

  it('写像確定後は queueTransition の未送信から同期済みへの遷移と合成できる', () => {
    const result = evaluateAfterMappingConfirmation(
      unsentSlot(),
      PLAYER_REGISTRATION_EVENT_KIND,
      { resolvePlayerRegistrationMapping: () => true },
    )

    expect(result.applied).toBe(true)
    if (result.applied) {
      expect(result.slot?.state).toBe(queueStateId('同期済み'))
    }
  })

  it('製品ファイルで D3 とイベント種別 ID の直書きをしない', () => {
    expect(mappingConfirmationGateSource).not.toContain('D3')
    expect(
      mappingConfirmationGateSource.match(/(['"`])(?:1[0-2]|[1-9])\1/g) ?? [],
    ).toHaveLength(0)
  })
})

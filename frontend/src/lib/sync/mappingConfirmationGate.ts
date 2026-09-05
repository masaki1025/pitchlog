// このゲートは docs/design/sync-protocol.md 4-4・7-1・7-2 の C4 の写しである。
// 写像の取得経路と値の形式は実装せず、確定済みかどうかを注入から受け取る。

import { EVENT_KIND_RULES, type EventKind } from './eventKinds'

function findPlayerRegistrationEventKind(): EventKind {
  const eventKind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === '選手のその場登録',
  )
  if (!eventKind) {
    throw new Error('選手登録イベント種別がありません')
  }
  return eventKind
}

const PLAYER_REGISTRATION_EVENT_KIND = findPlayerRegistrationEventKind()

type MappingConfirmationRuleDefinition = Readonly<{
  id: string
  rightHandSide: string
}>

export const C4_MAPPING_CONFIRMATION_RULE = {
  id: 'C4',
  rightHandSide: '写像が確定するまで+同期済みとして扱わない',
} as const satisfies MappingConfirmationRuleDefinition

export const MAPPING_CONFIRMATION_STATUS = {
  NOT_REQUIRED: '対象外',
  CONFIRMED: '確定',
  UNCONFIRMED: '未確定',
} as const

type MappingConfirmationStatus =
  (typeof MAPPING_CONFIRMATION_STATUS)[keyof typeof MAPPING_CONFIRMATION_STATUS]

export type MappingConfirmationRequest = Readonly<{
  eventKind: EventKind
  event: unknown
}>

export type PlayerRegistrationMappingResolver = (
  event: unknown,
) => boolean | undefined

export type MappingConfirmationInjections = Readonly<{
  resolvePlayerRegistrationMapping?: PlayerRegistrationMappingResolver
}>

export type MappingConfirmationGateResult = Readonly<{
  status: MappingConfirmationStatus
  allowsSyncedTransition: boolean
}>

function result(
  status: MappingConfirmationStatus,
  allowsSyncedTransition: boolean,
): MappingConfirmationGateResult {
  return Object.freeze({ status, allowsSyncedTransition })
}

export function checkMappingConfirmation(
  request: MappingConfirmationRequest,
  injections: MappingConfirmationInjections = {},
): MappingConfirmationGateResult {
  if (request.eventKind.id !== PLAYER_REGISTRATION_EVENT_KIND.id) {
    return result(MAPPING_CONFIRMATION_STATUS.NOT_REQUIRED, true)
  }

  let mappingConfirmed: boolean | undefined
  try {
    mappingConfirmed = injections.resolvePlayerRegistrationMapping?.(
      request.event,
    )
  } catch {
    return result(MAPPING_CONFIRMATION_STATUS.UNCONFIRMED, false)
  }

  return mappingConfirmed === true
    ? result(MAPPING_CONFIRMATION_STATUS.CONFIRMED, true)
    : result(MAPPING_CONFIRMATION_STATUS.UNCONFIRMED, false)
}

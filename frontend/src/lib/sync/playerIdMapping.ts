// この受け取り側は docs/design/sync-protocol.md 4-4・7-1 の A4 と C4 を表す。
// C1 の応答生成や値の物理形式は扱わず、写像を対象イベントへ結合して既存ゲートへ供給する。

import type { D1AckPlayerIdMapping } from './ackEnvelope'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import type {
  MappingConfirmationInjections,
  PlayerRegistrationMappingResolver,
} from './mappingConfirmationGate'
import type { QueueEventKey } from './queueTransition'
import type { TemporaryIdMappingRecord } from './temporaryIdMapping'

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

export type PlayerIdMappingTarget = Readonly<{
  eventKind: EventKind
  event: unknown
  key: QueueEventKey
  temporaryId?: unknown
}>

export type PlayerIdMappingResponse = Readonly<{
  key: QueueEventKey
  mappings: readonly D1AckPlayerIdMapping[]
}>

export type ConfirmedPlayerIdMapping = Readonly<{
  key: QueueEventKey
  mapping: TemporaryIdMappingRecord<unknown, unknown>
}>

export type PlayerIdMappingReception = Readonly<{
  confirmedMapping?: ConfirmedPlayerIdMapping
  mappingConfirmation: MappingConfirmationInjections
}>

export type PlayerIdMappingReceptionRequest = Readonly<{
  target: PlayerIdMappingTarget
  response?: PlayerIdMappingResponse
}>

function hasOwn(value: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, key)
}

function sameEventKey(first: QueueEventKey, second: QueueEventKey): boolean {
  return (
    Object.is(first.d4, second.d4) &&
    Object.is(first.d1, second.d1) &&
    Object.is(first.d5, second.d5)
  )
}

function mappingConfirmationFor(event: unknown): MappingConfirmationInjections {
  const resolvePlayerRegistrationMapping: PlayerRegistrationMappingResolver = (
    candidate,
  ) => (Object.is(candidate, event) ? true : undefined)
  return Object.freeze({ resolvePlayerRegistrationMapping })
}

export function receivePlayerIdMapping(
  request: PlayerIdMappingReceptionRequest,
): PlayerIdMappingReception {
  const { target, response } = request
  if (target.eventKind.id !== PLAYER_REGISTRATION_EVENT_KIND.id) {
    return Object.freeze({ mappingConfirmation: Object.freeze({}) })
  }
  if (!hasOwn(target, 'temporaryId')) {
    throw new Error('選手登録イベントの一時 ID がありません')
  }
  if (!response) {
    throw new Error('選手登録イベントの A4 写像がありません')
  }
  if (!sameEventKey(target.key, response.key)) {
    throw new Error('A4 写像が別の選手登録イベントに結合されています')
  }

  let confirmedMapping: D1AckPlayerIdMapping | undefined
  for (const mapping of response.mappings) {
    if (!Object.is(mapping.temporaryId, target.temporaryId)) {
      throw new Error('選手登録イベントに余分な A4 写像があります')
    }
    if (confirmedMapping) {
      throw new Error('選手登録イベントの A4 写像が重複しています')
    }
    confirmedMapping = mapping
  }
  if (!confirmedMapping) {
    throw new Error('選手登録イベントの A4 写像が欠落しています')
  }

  return Object.freeze({
    confirmedMapping: Object.freeze({
      key: target.key,
      mapping: confirmedMapping,
    }),
    mappingConfirmation: mappingConfirmationFor(target.event),
  })
}

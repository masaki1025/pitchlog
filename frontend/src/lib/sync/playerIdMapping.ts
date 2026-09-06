// この受け取り側は docs/design/sync-protocol.md 4-4・7-1 の A4 と C4 を表す。
// C1 の応答生成や値の物理形式は扱わず、写像を対象イベントへ結合して既存ゲートへ供給する。

import type { D1AckPlayerIdMapping } from './ackEnvelope'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import type {
  MappingConfirmationInjections,
  PlayerRegistrationMappingResolver,
} from './mappingConfirmationGate'
import type { QueueEventKey } from './queueTransition'
import { assertExactDefinedObject, assertInputArray } from './receptionInput'
import type { TemporaryIdMappingRecord } from './temporaryIdMapping'

function findPlayerRegistrationEventKind(): EventKind {
  const eventKind = EVENT_KIND_RULES.find((candidate) =>
    Object.is(candidate.name, '選手のその場登録'),
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

const RECEPTION_REQUEST_KEYS = Object.freeze(['target', 'response'] as const)
const PLAYER_RECEPTION_REQUEST_KEYS = RECEPTION_REQUEST_KEYS
const NON_PLAYER_RECEPTION_REQUEST_KEYS = Object.freeze(['target'] as const)
const TARGET_KEYS = Object.freeze([
  'eventKind',
  'event',
  'key',
  'temporaryId',
] as const)
const PLAYER_TARGET_KEYS = TARGET_KEYS
const NON_PLAYER_TARGET_KEYS = Object.freeze([
  'eventKind',
  'event',
  'key',
] as const)
const EVENT_KEY_KEYS = Object.freeze(['d4', 'd1', 'd5'] as const)
const RESPONSE_KEYS = Object.freeze(['key', 'mappings'] as const)
const MAPPING_KEYS = Object.freeze(['temporaryId', 'officialId'] as const)

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
  assertExactDefinedObject(
    request,
    RECEPTION_REQUEST_KEYS,
    NON_PLAYER_RECEPTION_REQUEST_KEYS,
    'A4 写像の受け取り要求が完全ではありません',
  )
  const { target, response } = request
  assertExactDefinedObject(
    target,
    TARGET_KEYS,
    NON_PLAYER_TARGET_KEYS,
    'A4 写像の対象（一時 ID を含む）が完全ではありません',
  )
  assertExactDefinedObject(
    target.key,
    EVENT_KEY_KEYS,
    EVENT_KEY_KEYS,
    'A4 写像の対象キーが完全ではありません',
  )

  if (!Object.is(target.eventKind.id, PLAYER_REGISTRATION_EVENT_KIND.id)) {
    assertExactDefinedObject(
      request,
      NON_PLAYER_RECEPTION_REQUEST_KEYS,
      NON_PLAYER_RECEPTION_REQUEST_KEYS,
      '選手登録以外のイベントに A4 写像を指定できません',
    )
    assertExactDefinedObject(
      target,
      NON_PLAYER_TARGET_KEYS,
      NON_PLAYER_TARGET_KEYS,
      '選手登録以外のイベントに一時 ID を指定できません',
    )
    return Object.freeze({ mappingConfirmation: Object.freeze({}) })
  }
  assertExactDefinedObject(
    request,
    PLAYER_RECEPTION_REQUEST_KEYS,
    PLAYER_RECEPTION_REQUEST_KEYS,
    '選手登録イベントの A4 写像がありません',
  )
  assertExactDefinedObject(
    target,
    PLAYER_TARGET_KEYS,
    PLAYER_TARGET_KEYS,
    '選手登録イベントの一時 ID がありません',
  )
  if (!response) {
    throw new Error('選手登録イベントの A4 写像がありません')
  }
  assertExactDefinedObject(
    response,
    RESPONSE_KEYS,
    RESPONSE_KEYS,
    '選手登録イベントの A4 応答が完全ではありません',
  )
  assertExactDefinedObject(
    response.key,
    EVENT_KEY_KEYS,
    EVENT_KEY_KEYS,
    '選手登録イベントの A4 応答キーが完全ではありません',
  )
  assertInputArray<D1AckPlayerIdMapping>(
    response.mappings,
    '選手登録イベントの A4 写像が配列ではありません',
  )
  for (const mapping of response.mappings) {
    assertExactDefinedObject(
      mapping,
      MAPPING_KEYS,
      MAPPING_KEYS,
      '選手登録イベントの A4 写像が完全ではありません',
    )
  }
  assertInputArray<D1AckPlayerIdMapping>(
    response.mappings,
    '選手登録イベントの A4 写像が配列ではありません',
    (first, second) => Object.is(first.temporaryId, second.temporaryId),
    '選手登録イベントの A4 写像が重複しています',
  )
  if (!sameEventKey(target.key, response.key)) {
    throw new Error('A4 写像が別の選手登録イベントに結合されています')
  }

  let confirmedMapping: D1AckPlayerIdMapping | undefined
  for (const mapping of response.mappings) {
    if (!Object.is(mapping.temporaryId, target.temporaryId)) {
      throw new Error('選手登録イベントに余分な A4 写像があります')
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

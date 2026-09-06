// この DTO とパーサは docs/design/sync-protocol.md 7-1 の D1 ACK 受け取り契約を表す。
// 識別値の物理形式は解釈せず、transport から本 DTO への変換は後続実装に委ねる。

import {
  readCanonAckStateResults,
  type CanonAckStateResult,
} from './canonOracle'
import { assertExactDefinedObject, assertInputArray } from './receptionInput'

const ACK_ENVELOPE_KEYS = Object.freeze([
  'advancedD3',
  'eventResults',
  'playerIdMappings',
] as const)
const ACK_REQUIRED_KEYS = Object.freeze(['advancedD3', 'eventResults'] as const)
const EVENT_RESULT_KEYS = Object.freeze(['d4', 'd1', 'd5', 'a5Result'] as const)
const PLAYER_ID_MAPPING_KEYS = Object.freeze([
  'temporaryId',
  'officialId',
] as const)

export type D1AckEventResult = Readonly<{
  d4: unknown
  d1: unknown
  d5: unknown
  a5Result: CanonAckStateResult
}>

export type D1AckPlayerIdMapping = Readonly<{
  temporaryId: unknown
  officialId: unknown
}>

export type D1AckEnvelope = Readonly<{
  advancedD3: unknown
  eventResults: readonly D1AckEventResult[]
  playerIdMappings?: readonly D1AckPlayerIdMapping[]
}>

function parseEventResult(
  candidate: unknown,
  canonResults: readonly CanonAckStateResult[],
): D1AckEventResult {
  assertExactDefinedObject(
    candidate,
    EVENT_RESULT_KEYS,
    EVENT_RESULT_KEYS,
    'ACK のイベント結果が不足しているか、余分な要素があります',
  )

  const result = canonResults.find((canonResult) =>
    Object.is(canonResult.id, candidate.a5Result),
  )
  if (!result) {
    throw new Error('ACK に未知の A5 結果があります')
  }

  return Object.freeze({
    d4: candidate.d4,
    d1: candidate.d1,
    d5: candidate.d5,
    a5Result: result,
  })
}

function parsePlayerIdMapping(candidate: unknown): D1AckPlayerIdMapping {
  assertExactDefinedObject(
    candidate,
    PLAYER_ID_MAPPING_KEYS,
    PLAYER_ID_MAPPING_KEYS,
    'ACK の A4 写像が不足しているか、余分な要素があります',
  )

  return Object.freeze({
    temporaryId: candidate.temporaryId,
    officialId: candidate.officialId,
  })
}

export function parseD1AckEnvelope(candidate: unknown): D1AckEnvelope {
  assertExactDefinedObject(
    candidate,
    ACK_ENVELOPE_KEYS,
    ACK_REQUIRED_KEYS,
    'ACK に前進後の D3 またはイベントごとの A5 結果がありません',
  )
  assertInputArray(
    candidate.eventResults,
    'ACK にイベントごとの A5 結果がありません',
  )

  const canonResults = readCanonAckStateResults()
  const eventResults = candidate.eventResults.map((eventResult) =>
    parseEventResult(eventResult, canonResults),
  )
  assertInputArray<D1AckEventResult>(
    eventResults,
    'ACK のイベント結果が配列ではありません',
    (first, second) =>
      Object.is(first.d4, second.d4) &&
      Object.is(first.d1, second.d1) &&
      Object.is(first.d5, second.d5),
    'ACK のイベント結果が重複しています',
  )

  const frozenEventResults = Object.freeze(eventResults)
  if (Object.is(candidate.playerIdMappings, undefined)) {
    return Object.freeze({
      advancedD3: candidate.advancedD3,
      eventResults: frozenEventResults,
    })
  }
  assertInputArray(
    candidate.playerIdMappings,
    'ACK の A4 写像が配列ではありません',
  )

  const playerIdMappings = candidate.playerIdMappings.map(parsePlayerIdMapping)
  assertInputArray<D1AckPlayerIdMapping>(
    playerIdMappings,
    'ACK の A4 写像が配列ではありません',
    (first, second) => Object.is(first.temporaryId, second.temporaryId),
    'ACK の A4 写像が重複しています',
  )
  return Object.freeze({
    advancedD3: candidate.advancedD3,
    eventResults: frozenEventResults,
    playerIdMappings: Object.freeze(playerIdMappings),
  })
}

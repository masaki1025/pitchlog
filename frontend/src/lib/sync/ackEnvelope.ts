// この DTO とパーサは docs/design/sync-protocol.md 7-1 の D1 ACK 受け取り契約を表す。
// 識別値の物理形式は解釈せず、transport から本 DTO への変換は後続実装に委ねる。

import {
  readCanonAckStateResults,
  type CanonAckStateResult,
} from './canonOracle'

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

function isRecord(value: unknown): value is Record<PropertyKey, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasOwn(value: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, key)
}

function parseEventResult(
  candidate: unknown,
  canonResults: readonly CanonAckStateResult[],
  parsedResults: readonly D1AckEventResult[],
): D1AckEventResult {
  if (
    !isRecord(candidate) ||
    !hasOwn(candidate, 'd4') ||
    !hasOwn(candidate, 'd1') ||
    !hasOwn(candidate, 'd5') ||
    !hasOwn(candidate, 'a5Result')
  ) {
    throw new Error('ACK のイベント結果が不足しています')
  }

  const result = canonResults.find(
    (canonResult) => canonResult.id === candidate.a5Result,
  )
  if (!result) {
    throw new Error('ACK に未知の A5 結果があります')
  }

  const duplicate = parsedResults.some(
    (parsedResult) =>
      Object.is(parsedResult.d4, candidate.d4) &&
      Object.is(parsedResult.d1, candidate.d1) &&
      Object.is(parsedResult.d5, candidate.d5),
  )
  if (duplicate) {
    throw new Error('ACK のイベント結果が重複しています')
  }

  return Object.freeze({
    d4: candidate.d4,
    d1: candidate.d1,
    d5: candidate.d5,
    a5Result: result,
  })
}

function parsePlayerIdMapping(candidate: unknown): D1AckPlayerIdMapping {
  if (
    !isRecord(candidate) ||
    !hasOwn(candidate, 'temporaryId') ||
    !hasOwn(candidate, 'officialId')
  ) {
    throw new Error('ACK の A4 写像が不足しています')
  }

  return Object.freeze({
    temporaryId: candidate.temporaryId,
    officialId: candidate.officialId,
  })
}

export function parseD1AckEnvelope(candidate: unknown): D1AckEnvelope {
  if (!isRecord(candidate) || !hasOwn(candidate, 'advancedD3')) {
    throw new Error('ACK に前進後の D3 がありません')
  }
  if (!Array.isArray(candidate.eventResults)) {
    throw new Error('ACK にイベントごとの A5 結果がありません')
  }

  const canonResults = readCanonAckStateResults()
  const eventResults: D1AckEventResult[] = []
  for (const eventResult of candidate.eventResults) {
    eventResults.push(parseEventResult(eventResult, canonResults, eventResults))
  }

  const frozenEventResults = Object.freeze(eventResults)
  if (!hasOwn(candidate, 'playerIdMappings')) {
    return Object.freeze({
      advancedD3: candidate.advancedD3,
      eventResults: frozenEventResults,
    })
  }
  if (!Array.isArray(candidate.playerIdMappings)) {
    throw new Error('ACK の A4 写像が配列ではありません')
  }

  const playerIdMappings = Object.freeze(
    candidate.playerIdMappings.map(parsePlayerIdMapping),
  )
  return Object.freeze({
    advancedD3: candidate.advancedD3,
    eventResults: frozenEventResults,
    playerIdMappings,
  })
}

import { canonicalContinuationUuid, sameContinuationValue } from './ordinaryPitchContinuation'
import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import { deriveOrdinaryPitch } from './publicApi'

type Json = Record<string, unknown>

function object(value: unknown, keys: Array<string>): Json | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  const row = value as Json
  if (
    !Object.keys(row).every((key) => keys.includes(key)) ||
    keys.some((key) => !Object.hasOwn(row, key))
  )
    return null
  return row
}

function event(value: unknown): Json | null {
  const row = object(value, ['eventKind', 'resultId', 'pitchEventKind'])
  if (
    row === null ||
    row.eventKind !== 'batting-result' ||
    typeof row.resultId !== 'string' ||
    row.pitchEventKind !== 'pitch-event'
  )
    return null
  return row
}

function evaluated(
  source: Json,
  before: unknown,
): { after: Json; frame: Json } | null {
  let response: unknown
  try {
    response = JSON.parse(
      deriveOrdinaryPitch(
        JSON.stringify(
          Object.assign({}, source, { before: before, history: { stack: [] } }),
        ),
      ),
    )
  } catch {
    return null
  }
  const envelope = object(response, ['ok', 'value'])
  if (envelope === null || envelope.ok !== true) return null
  const frame = envelope.value
  if (frame === null || typeof frame !== 'object' || Array.isArray(frame))
    return null
  const value = frame as Json
  const after = object(value.after, ['stateFields', 'scoreboard'])
  if (after === null || !Array.isArray(value.historyContext)) return null
  let historyCount = 0n
  for (const entry of value.historyContext) {
    if (entry === null || typeof entry !== 'object') return null
    historyCount = historyCount + 1n
  }
  if (historyCount !== 1n) return null
  return { after, frame: value }
}

function failure(code: string): string {
  return JSON.stringify({ ok: false, error: { code } })
}

/**
 * 保存済み原本の有限ページを既T1で照合し、訂正系列を同じ核で再導出する。
 *
 * 本操作は真正なDB読取・帰属/成績・T2・P3受理資格を発行しない。呼出側は
 * 各ページの原本/D2順/前後連鎖を同じ試合の真正原本へ束縛する。
 */
export function replayOrdinaryCorrectionPage(
  raw: unknown,
): string {
  const request = object(raw, [
    'version',
    'originalBefore',
    'correctedBefore',
    'previousD2',
    'targetIncluded',
    'records',
  ])
  if (
    request === null ||
    request.version !== 'past-correction-ordinary-page-v1' ||
    typeof request.targetIncluded !== 'boolean' ||
    !Array.isArray(request.records) ||
    !request.records.some(() => true) ||
    object(request.originalBefore, ['stateFields', 'scoreboard']) === null ||
    object(request.correctedBefore, ['stateFields', 'scoreboard']) === null ||
    (request.targetIncluded &&
      !sameContinuationValue(request.originalBefore, request.correctedBefore))
  )
    return failure('INVALID_REQUEST')
  const initialD2 = parseDecimalInteger(request.previousD2)
  if (initialD2 === null || initialD2 < 0n)
    return failure('INVALID_DECIMAL_INTEGER')
  let lastD2 = initialD2
  let originalBefore: unknown = request.originalBefore
  let correctedBefore: unknown = request.correctedBefore
  let results: Array<Json> = []
  let seen: Array<string> = []
  let first = true
  let pageCount = 0n
  for (const source of request.records) {
    pageCount = pageCount + 1n
    if (pageCount > 25n) return failure('INVALID_REQUEST')
    const row = object(source, [
      'sourceEventId',
      'sourceD2',
      'original',
      'storedAfter',
      'replacement',
    ])
    if (
      row === null ||
      typeof row.sourceEventId !== 'string' ||
      !canonicalContinuationUuid(row.sourceEventId) ||
      seen.includes(row.sourceEventId) ||
      event(row.original) === null ||
      object(row.storedAfter, ['stateFields', 'scoreboard']) === null ||
      (request.targetIncluded && first && event(row.replacement) === null) ||
      ((!request.targetIncluded || !first) && row.replacement !== null)
    )
      return failure('INVALID_REQUEST')
    const d2 = parseDecimalInteger(row.sourceD2)
    if (d2 === null || d2 <= lastD2)
      return failure('INVALID_DECIMAL_INTEGER')
    lastD2 = d2
    seen = seen.concat([row.sourceEventId])
    const original = evaluated(row.original as Json, originalBefore)
    if (
      original === null ||
      !sameContinuationValue(original.after, row.storedAfter)
    )
      return failure('SOURCE_MISMATCH')
    let selected = row.original
    if (row.replacement !== null) selected = row.replacement
    const corrected = evaluated(selected as Json, correctedBefore)
    if (corrected === null) return failure('CORRECTION_UNSUPPORTED')
    results = results.concat([
      {
        sourceEventId: row.sourceEventId,
        sourceD2: row.sourceD2,
        original: original.frame,
        corrected: corrected.frame,
      },
    ])
    originalBefore = original.after
    correctedBefore = corrected.after
    first = false
  }
  return JSON.stringify({
    ok: true,
    value: {
      originalAfter: originalBefore,
      correctedAfter: correctedBefore,
      lastD2: formatDecimalInteger(lastD2),
      frames: results,
    },
  })
}

import { parseD1AckEnvelope } from '../lib/sync/ackEnvelope'
import {
  CANON_ACK_STATE_RESULT,
  readCanonBoundaryResults,
} from '../lib/sync/canonOracle'
import { canonicalUuid } from './authIntent'
import type { AckResponse } from '../screens/GameScreenAckApplication'

/** 水位と対象slotの受理結果を区別する。後続水位で他slotを成功へ補完しない。 */
export function readOrdinaryPitchAck(
  value: unknown,
  key: Readonly<{ d4: string; d1: number; d5: string }>,
): AckResponse | undefined {
  try {
    if (
      typeof key.d4 !== 'string' ||
      Array.from(key.d4).length < 1 ||
      Array.from(key.d4).length > 128 ||
      !Number.isSafeInteger(key.d1) ||
      key.d1 < 1 ||
      typeof key.d5 !== 'string' ||
      key.d5.length !== 36 ||
      !canonicalUuid.test(key.d5)
    )
      return undefined
    const envelope = parseD1AckEnvelope(value)
    if (
      envelope.eventResults.length !== 1 ||
      typeof envelope.advancedD3 !== 'number' ||
      !Number.isSafeInteger(envelope.advancedD3) ||
      envelope.advancedD3 < key.d1
    )
      return undefined
    const item = envelope.eventResults[0]!
    if (
      item.d4 !== key.d4 ||
      item.d1 !== key.d1 ||
      item.d5 !== key.d5 ||
      (item.a5Result.id !== CANON_ACK_STATE_RESULT.ACCEPTED &&
        item.a5Result.id !== CANON_ACK_STATE_RESULT.DUPLICATE)
    )
      return undefined
    const terminal = readCanonBoundaryResults().find(
      (row) => row.name === '要求終端',
    )
    if (!terminal) return undefined
    return { envelope: value, boundaryResult: terminal.id }
  } catch {
    return undefined
  }
}

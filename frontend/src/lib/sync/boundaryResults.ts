// この受け取り側は docs/design/sync-protocol.md 7-1 の A3 を表す。
// 境界結果の決定は行わず、R-BOUNDARY で確認した結果を ACK の有無で区分する。

import {
  readCanonBoundaryResults,
  type CanonBoundaryResult,
} from './canonOracle'
import { assertExactDefinedObject, assertInputArray } from './receptionInput'

export type AckBoundaryResult = Readonly<{
  delivery: 'ack'
  boundaryResult: CanonBoundaryResult
}>

export type NoAckBoundaryResult = Readonly<{
  delivery: 'no-ack'
  boundaryResult: CanonBoundaryResult
}>

type BoundaryResult = AckBoundaryResult | NoAckBoundaryResult

const CANON_BOUNDARY_RESULT_KEYS = Object.freeze(['id', 'name'] as const)
const ACK_BOUNDARY_RESULT_NAMES = Object.freeze([
  '要求終端',
  'gap',
  '恒久的な内容拒否',
  '記録権不一致',
] as const)

function isAckBoundaryResult(result: CanonBoundaryResult): boolean {
  return ACK_BOUNDARY_RESULT_NAMES.some((name) => Object.is(name, result.name))
}

function hasAckDelivery(result: BoundaryResult): result is AckBoundaryResult {
  return Object.is(result.delivery, 'ack')
}

function hasNoAckDelivery(
  result: BoundaryResult,
): result is NoAckBoundaryResult {
  return Object.is(result.delivery, 'no-ack')
}

const canonBoundaryResults = readCanonBoundaryResults()
for (const boundaryResult of canonBoundaryResults) {
  assertExactDefinedObject(
    boundaryResult,
    CANON_BOUNDARY_RESULT_KEYS,
    CANON_BOUNDARY_RESULT_KEYS,
    'R-BOUNDARY の境界結果が完全ではありません',
  )
}
assertInputArray<CanonBoundaryResult>(
  canonBoundaryResults,
  'R-BOUNDARY の境界結果が配列ではありません',
  (first, second) => Object.is(first.id, second.id),
  'R-BOUNDARY の境界結果が重複しています',
)
if (
  ACK_BOUNDARY_RESULT_NAMES.some(
    (name) =>
      !canonBoundaryResults.some((boundaryResult) =>
        Object.is(boundaryResult.name, name),
      ),
  )
) {
  throw new Error('R-BOUNDARY に ACK 許可結果が不足しています')
}

const boundaryResults: readonly BoundaryResult[] = Object.freeze(
  canonBoundaryResults.map((boundaryResult) =>
    Object.freeze(
      isAckBoundaryResult(boundaryResult)
        ? { delivery: 'ack' as const, boundaryResult }
        : { delivery: 'no-ack' as const, boundaryResult },
    ),
  ),
)

export const ACK_BOUNDARY_RESULTS: readonly AckBoundaryResult[] = Object.freeze(
  boundaryResults.filter(hasAckDelivery),
)

export const NO_ACK_BOUNDARY_RESULTS: readonly NoAckBoundaryResult[] =
  Object.freeze(boundaryResults.filter(hasNoAckDelivery))

export function parseAckBoundaryResult(candidate: unknown): AckBoundaryResult {
  const result = boundaryResults.find((boundaryResult) =>
    Object.is(boundaryResult.boundaryResult.id, candidate),
  )
  if (!result) {
    throw new Error('未知の D1 境界結果です')
  }
  if (!hasAckDelivery(result)) {
    throw new Error('この境界結果では ACK が返りません')
  }
  return result
}

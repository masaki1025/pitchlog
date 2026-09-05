// この受け取り側は docs/design/sync-protocol.md 7-1 の A3 を表す。
// 境界結果の決定は行わず、R-BOUNDARY で確認した結果を ACK の有無で区分する。

import {
  readCanonBoundaryResults,
  type CanonBoundaryResult,
} from './canonOracle'

export type AckBoundaryResult = Readonly<{
  delivery: 'ack'
  boundaryResult: CanonBoundaryResult
}>

export type NoAckBoundaryResult = Readonly<{
  delivery: 'no-ack'
  boundaryResult: CanonBoundaryResult
}>

type BoundaryResult = AckBoundaryResult | NoAckBoundaryResult

const LAST_ACK_BOUNDARY_SEQUENCE = 4

function isAckBoundaryResult(result: CanonBoundaryResult): boolean {
  return Number(result.id.slice(1)) <= LAST_ACK_BOUNDARY_SEQUENCE
}

const boundaryResults: readonly BoundaryResult[] = Object.freeze(
  readCanonBoundaryResults().map((boundaryResult) =>
    Object.freeze(
      isAckBoundaryResult(boundaryResult)
        ? { delivery: 'ack' as const, boundaryResult }
        : { delivery: 'no-ack' as const, boundaryResult },
    ),
  ),
)

export const ACK_BOUNDARY_RESULTS: readonly AckBoundaryResult[] = Object.freeze(
  boundaryResults.filter(
    (result): result is AckBoundaryResult => result.delivery === 'ack',
  ),
)

export const NO_ACK_BOUNDARY_RESULTS: readonly NoAckBoundaryResult[] =
  Object.freeze(
    boundaryResults.filter(
      (result): result is NoAckBoundaryResult => result.delivery === 'no-ack',
    ),
  )

export function parseAckBoundaryResult(candidate: unknown): AckBoundaryResult {
  const result = boundaryResults.find((boundaryResult) =>
    Object.is(boundaryResult.boundaryResult.id, candidate),
  )
  if (!result) {
    throw new Error('未知の D1 境界結果です')
  }
  if (result.delivery === 'no-ack') {
    throw new Error('この境界結果では ACK が返りません')
  }
  return result
}

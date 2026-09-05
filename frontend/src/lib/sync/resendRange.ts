// この選択器は docs/design/sync-protocol.md 7-3 のクライアント側手順 1・4を表す。
// D3 は再送範囲にだけ使い、状態遷移やサーバー側の応答決定は扱わない。

import type { D1AckEnvelope } from './ackEnvelope'
import type { DurableQueueSlot } from './durableQueue'
import { queueStateId } from './queueState'

const UNSENT_STATE = queueStateId('未送信')

export type ResendD3Checkpoint = Readonly<{
  d4: unknown
  d3: unknown
}>

export type D1AfterD3Resolver = (
  d1: DurableQueueSlot['d1'],
  d3: ResendD3Checkpoint['d3'],
) => boolean | undefined

export type ResendRangeRequest = Readonly<{
  d4: unknown
  orderedSlots: readonly DurableQueueSlot[]
  lastKnownSynced?: ResendD3Checkpoint
  ack?: D1AckEnvelope
  isD1AfterD3: D1AfterD3Resolver
}>

export type ResendRangeResult =
  | Readonly<{
      status: 'ready'
      checkpoint: ResendD3Checkpoint
      slots: readonly DurableQueueSlot[]
    }>
  | Readonly<{
      status: 'unavailable'
      reason: 'd3-unknown' | 'd4-mismatch' | 'order-unknown'
      slots: readonly []
    }>

function unavailable(
  reason: Extract<ResendRangeResult, { status: 'unavailable' }>['reason'],
): ResendRangeResult {
  return Object.freeze({
    status: 'unavailable',
    reason,
    slots: Object.freeze([] as const),
  })
}

function resolveCheckpoint(
  request: ResendRangeRequest,
): ResendD3Checkpoint | undefined {
  if (request.ack) {
    return Object.freeze({ d4: request.d4, d3: request.ack.advancedD3 })
  }
  return request.lastKnownSynced
    ? Object.freeze({
        d4: request.lastKnownSynced.d4,
        d3: request.lastKnownSynced.d3,
      })
    : undefined
}

export function determineResendRange(
  request: ResendRangeRequest,
): ResendRangeResult {
  const checkpoint = resolveCheckpoint(request)
  if (!checkpoint) {
    return unavailable('d3-unknown')
  }
  if (!Object.is(checkpoint.d4, request.d4)) {
    return unavailable('d4-mismatch')
  }

  const slots: DurableQueueSlot[] = []
  for (const slot of request.orderedSlots) {
    if (!Object.is(slot.d4, request.d4) || slot.state !== UNSENT_STATE) {
      continue
    }

    let isAfter: boolean | undefined
    try {
      isAfter = request.isD1AfterD3(slot.d1, checkpoint.d3)
    } catch {
      return unavailable('order-unknown')
    }
    if (isAfter === undefined) {
      return unavailable('order-unknown')
    }
    if (isAfter) {
      slots.push(slot)
    }
  }

  return Object.freeze({
    status: 'ready',
    checkpoint,
    slots: Object.freeze(slots),
  })
}

// この選択器は docs/design/sync-protocol.md 7-3 のクライアント側手順 1・4を表す。
// D3 は再送範囲にだけ使い、状態遷移やサーバー側の応答決定は扱わない。

import type { D1AckEnvelope } from './ackEnvelope'
import type { DurableQueueSlot } from './durableQueue'
import { queueStateId } from './queueState'
import { assertExactDefinedObject, assertInputArray } from './receptionInput'

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

const RESEND_REQUEST_KEYS = Object.freeze([
  'd4',
  'orderedSlots',
  'lastKnownSynced',
  'ack',
  'isD1AfterD3',
] as const)
const RESEND_REQUIRED_KEYS = Object.freeze([
  'd4',
  'orderedSlots',
  'isD1AfterD3',
] as const)
const CHECKPOINT_KEYS = Object.freeze(['d4', 'd3'] as const)
const ACK_ENVELOPE_KEYS = Object.freeze([
  'advancedD3',
  'eventResults',
  'playerIdMappings',
] as const)
const ACK_REQUIRED_KEYS = Object.freeze(['advancedD3', 'eventResults'] as const)
const QUEUE_SLOT_KEYS = Object.freeze([
  'game',
  'd4',
  'd1',
  'd5',
  'version',
  'event',
  'state',
  'actionRequiredLabel',
] as const)
const QUEUE_SLOT_REQUIRED_KEYS = Object.freeze([
  'game',
  'd4',
  'd1',
  'd5',
  'version',
  'event',
  'state',
] as const)

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
  assertExactDefinedObject(
    request,
    RESEND_REQUEST_KEYS,
    RESEND_REQUIRED_KEYS,
    '再送範囲の入力が不足しているか、余分な要素があります',
  )
  assertInputArray(request.orderedSlots, '再送対象が配列ではありません')
  for (const slot of request.orderedSlots) {
    assertExactDefinedObject(
      slot,
      QUEUE_SLOT_KEYS,
      QUEUE_SLOT_REQUIRED_KEYS,
      '再送対象スロットが不足しているか、余分な要素があります',
    )
  }
  assertInputArray<DurableQueueSlot>(
    request.orderedSlots,
    '再送対象が配列ではありません',
    (first, second) =>
      Object.is(first.d4, second.d4) && Object.is(first.d1, second.d1),
    '再送対象スロットが重複しています',
  )
  if (!Object.is(request.lastKnownSynced, undefined)) {
    assertExactDefinedObject(
      request.lastKnownSynced,
      CHECKPOINT_KEYS,
      CHECKPOINT_KEYS,
      '既知の同期済み位置に D4 または D3 がありません',
    )
  }
  if (!Object.is(request.ack, undefined)) {
    assertExactDefinedObject(
      request.ack,
      ACK_ENVELOPE_KEYS,
      ACK_REQUIRED_KEYS,
      'ACK に D3 がないか、余分な要素があります',
    )
  }

  const checkpoint = resolveCheckpoint(request)
  if (!checkpoint) {
    return unavailable('d3-unknown')
  }
  if (!Object.is(checkpoint.d4, request.d4)) {
    return unavailable('d4-mismatch')
  }

  const slots: DurableQueueSlot[] = []
  for (const slot of request.orderedSlots) {
    if (
      !Object.is(slot.d4, request.d4) ||
      !Object.is(slot.state, UNSENT_STATE)
    ) {
      continue
    }

    let isAfter: boolean | undefined
    try {
      isAfter = request.isD1AfterD3(slot.d1, checkpoint.d3)
    } catch {
      return unavailable('order-unknown')
    }
    if (!Object.is(isAfter, true) && !Object.is(isAfter, false)) {
      return unavailable('order-unknown')
    }
    if (Object.is(isAfter, true)) {
      slots.push(slot)
    }
  }

  return Object.freeze({
    status: 'ready',
    checkpoint,
    slots: Object.freeze(slots),
  })
}

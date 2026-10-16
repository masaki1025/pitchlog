// E-1 `POST /games/{game_id}/sync/events` への送信の配線。
//
// 要求本文の形は docs/features/sync-wire-schema/design.md 3-2 が正。スロットと
// wire のキーの 1 対 1 対応も同節の表による。1 要求は単一の `(試合, D4)` に限る
// (docs/design/sync-protocol.md 6-2)。
//
// 本モジュールはキューに触れない。送るスロットは呼出元が渡し、送信の成否で
// キューの状態を変えるのは ACK を適用する側の仕事である(plan.md ステップ 5)。
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import { SYNC_EVENT_PATH, type EventSlotId } from '../lib/sync/eventFieldRules'
import type { EventKind } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'
import {
  checkSyncEvent,
  type SyncEventViolation,
} from '../lib/sync/validateSyncEvent'
import { apiRequest } from './client'

/** スロットと wire のキーの対応(sync-wire-schema/design.md 3-2・3-3 の表)。 */
const WIRE_KEY_BY_SLOT_ID = {
  V1: 'd5',
  V2: 'd1',
  V3: 'd4',
  V4: 'game_id',
  V5: 'event_kind',
  V6: 'd2',
  V7: 'payload',
  V8: 'state_diff',
  V9: 'replacement_state',
  V10: 'target_reference',
  V11: 'expected_version',
} as const satisfies Readonly<Record<EventSlotId, string>>

const D1_SLOT_ID = 'V2' satisfies EventSlotId
const D4_SLOT_ID = 'V3' satisfies EventSlotId
const GAME_ID_SLOT_ID = 'V4' satisfies EventSlotId

export type SyncEventRequestBody = Readonly<{
  recording_right_proof: unknown
  events: readonly Readonly<Record<string, unknown>>[]
}>

export const SYNC_EVENT_SEND_FAILURE = {
  /** 送るスロットが無い(`events` は空にしない)。 */
  EMPTY_REQUEST: 'empty-request',
  /** 1 要求に複数の `(試合, D4)` が混ざっている。 */
  MIXED_SCOPE: 'mixed-scope',
  /** 要求の中で D1 が重複している。 */
  DUPLICATE_D1: 'duplicate-d1',
  /** イベントの試合の識別が path と食い違う。 */
  GAME_ID_MISMATCH: 'game-id-mismatch',
  /** イベントの D4 がスロットの D4 と食い違う。 */
  D4_MISMATCH: 'd4-mismatch',
  /** 完成形が正本の検査を通らない。 */
  INVALID_EVENT: 'invalid-event',
  /** 送ったが応答を得られなかった。 */
  TRANSPORT_FAILED: 'transport-failed',
} as const

export type SyncEventSendFailure =
  (typeof SYNC_EVENT_SEND_FAILURE)[keyof typeof SYNC_EVENT_SEND_FAILURE]

export type SyncEventSendRequest = Readonly<{
  /** path の `{game_id}`。 */
  gameId: string
  /** V12。不透明な値のまま運ぶ。 */
  recordingRightProof: unknown
  /** 送るスロット。単一の `(試合, D4)` に限る。 */
  slots: readonly DurableQueueSlot[]
  /** 受理する種別の集合。採否が未裁定の種別を既定で混ぜないため呼出元が渡す。 */
  eventKinds: readonly EventKind[]
}>

export type SyncEventSendResult =
  | Readonly<{
      sent: true
      requestBody: SyncEventRequestBody
      response: unknown
    }>
  | Readonly<{
      sent: false
      reason: SyncEventSendFailure
      violation?: SyncEventViolation
      slotD1?: number
      error?: unknown
    }>

/** スロットの D1 を V2 へ入れた完成形。D1 は追記のときに採番されている。 */
function completeEvent(slot: DurableQueueSlot): SyncEvent {
  return { fields: { ...slot.event.fields, [D1_SLOT_ID]: slot.d1 } }
}

function toWireEvent(event: SyncEvent): Readonly<Record<string, unknown>> {
  const wire: Record<string, unknown> = {}
  for (const [slotId, value] of Object.entries(event.fields)) {
    // 値を持たないキーは省く。null を「持たない」の意味に使わない。
    const wireKey = WIRE_KEY_BY_SLOT_ID[slotId as EventSlotId]
    wire[wireKey] = value
  }
  return wire
}

function failure(
  reason: SyncEventSendFailure,
  detail: Omit<
    Extract<SyncEventSendResult, { sent: false }>,
    'sent' | 'reason'
  > = {},
): SyncEventSendResult {
  return { sent: false, reason, ...detail }
}

function buildRequestBody(
  request: SyncEventSendRequest,
): SyncEventRequestBody | SyncEventSendResult {
  if (request.slots.length === 0) {
    return failure(SYNC_EVENT_SEND_FAILURE.EMPTY_REQUEST)
  }

  const [first] = request.slots
  const seenD1 = new Set<number>()
  const events: Record<string, unknown>[] = []

  for (const slot of request.slots) {
    if (
      !Object.is(slot.game, request.gameId) ||
      !Object.is(slot.d4, first!.d4)
    ) {
      return failure(SYNC_EVENT_SEND_FAILURE.MIXED_SCOPE, { slotD1: slot.d1 })
    }
    if (seenD1.has(slot.d1)) {
      return failure(SYNC_EVENT_SEND_FAILURE.DUPLICATE_D1, { slotD1: slot.d1 })
    }
    seenD1.add(slot.d1)

    const event = completeEvent(slot)
    if (!Object.is(event.fields[GAME_ID_SLOT_ID], request.gameId)) {
      return failure(SYNC_EVENT_SEND_FAILURE.GAME_ID_MISMATCH, {
        slotD1: slot.d1,
      })
    }
    if (!Object.is(event.fields[D4_SLOT_ID], slot.d4)) {
      return failure(SYNC_EVENT_SEND_FAILURE.D4_MISMATCH, { slotD1: slot.d1 })
    }

    const checked = checkSyncEvent(event, {
      path: SYNC_EVENT_PATH.P2,
      eventKinds: request.eventKinds,
    })
    if (!checked.ok) {
      return failure(SYNC_EVENT_SEND_FAILURE.INVALID_EVENT, {
        violation: checked.reason,
        slotD1: slot.d1,
      })
    }

    events.push({ ...toWireEvent(event) })
  }

  return {
    recording_right_proof: request.recordingRightProof,
    events,
  }
}

/**
 * E-1 へ同期イベントを送る。
 *
 * 本文を組み立てられない場合は送らずに理由を返す。通信に失敗した場合も結果を
 * 返すだけで、キューの状態は変えない(未送信のまま)。
 *
 * Args:
 *     request: 送る範囲とスロット。
 *
 * Returns:
 *     送信の可否と、送った本文または理由。
 */
export async function postSyncEvents(
  request: SyncEventSendRequest,
): Promise<SyncEventSendResult> {
  const built = buildRequestBody(request)
  if ('sent' in built) {
    return built
  }

  try {
    const response = await apiRequest<unknown>(
      'POST',
      `/games/${encodeURIComponent(request.gameId)}/sync/events`,
      { body: built },
    )
    return { sent: true, requestBody: built, response }
  } catch (error) {
    return failure(SYNC_EVENT_SEND_FAILURE.TRANSPORT_FAILED, { error })
  }
}

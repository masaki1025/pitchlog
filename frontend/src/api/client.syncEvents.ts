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
import { ApiError, apiRequest, type SyncRequestCredentials } from './client'

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

/**
 * 正本の ID と wire のキーの対応から引いたスロット ID。
 *
 * 同じ対応を二重に宣言すると片方だけ直してずれるため、ここを唯一の宣言とし、
 * 画面側もここから import する。
 */
export const SYNC_EVENT_SLOT_ID = {
  D5: 'V1',
  D1: 'V2',
  D4: 'V3',
  GAME_ID: 'V4',
  D2: 'V6',
  PAYLOAD: 'V7',
  STATE_DIFF: 'V8',
} as const satisfies Readonly<Record<string, EventSlotId>>

const D5_SLOT_ID = SYNC_EVENT_SLOT_ID.D5
const D1_SLOT_ID = SYNC_EVENT_SLOT_ID.D1
const D4_SLOT_ID = SYNC_EVENT_SLOT_ID.D4
const GAME_ID_SLOT_ID = SYNC_EVENT_SLOT_ID.GAME_ID

export type SyncEventRequestBody = Readonly<{
  recording_right_proof: unknown
  events: readonly Readonly<Record<string, unknown>>[]
}>

export const SYNC_EVENT_SEND_FAILURE = {
  /** 送るスロットが無い(`events` は空にしない)。 */
  EMPTY_REQUEST: 'empty-request',
  /** 1 要求に複数の D4 が混ざっている。 */
  MIXED_SCOPE: 'mixed-scope',
  /** 要求の中で D1 が重複している。 */
  DUPLICATE_D1: 'duplicate-d1',
  /** スロットまたはイベントの試合の識別が path と食い違う。 */
  GAME_ID_MISMATCH: 'game-id-mismatch',
  /** イベントの D4 がスロットの D4 と食い違う。 */
  D4_MISMATCH: 'd4-mismatch',
  /** イベントの D5 がスロットの D5 と食い違う。 */
  D5_MISMATCH: 'd5-mismatch',
  /** D1 が L-2 の整数でない。 */
  INVALID_D1: 'invalid-d1',
  /** スロットの値が `undefined` で、JSON へ載せると黙って消える。 */
  UNDEFINED_SLOT_VALUE: 'undefined-slot-value',
  /** 完成形が正本の検査を通らない。 */
  INVALID_EVENT: 'invalid-event',
  /** 送ったが応答が返らなかった(通信断・中断)。 */
  NO_RESPONSE: 'no-response',
  /** 応答は返ったが、クライアントが解釈しない(S-1 違反を含む)。 */
  RESPONSE_NOT_INTERPRETED: 'response-not-interpreted',
} as const

export type SyncEventSendFailure =
  (typeof SYNC_EVENT_SEND_FAILURE)[keyof typeof SYNC_EVENT_SEND_FAILURE]

export type SyncEventSendRequest = Readonly<{
  /** 実端末資格と、送信前に耐久固定した要求attempt。 */
  syncCredentials?: SyncRequestCredentials
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
      /** 応答が返った場合の状態コード。顕在化に使う(NFR-015)。 */
      status?: number
      error?: unknown
    }>

/** スロットの D1 を V2 へ入れた完成形。D1 は追記のときに採番されている。 */
function completeEvent(slot: DurableQueueSlot): SyncEvent {
  return { fields: { ...slot.event.fields, [D1_SLOT_ID]: slot.d1 } }
}

function toWireEvent(event: SyncEvent): Readonly<Record<string, unknown>> {
  const wire: Record<string, unknown> = {}
  for (const [slotId, value] of Object.entries(event.fields)) {
    const wireKey = WIRE_KEY_BY_SLOT_ID[slotId as EventSlotId]
    wire[wireKey] = value
  }
  return wire
}

/**
 * `undefined` の値を持つスロットを探す。
 *
 * `checkSyncEvent` は値を見ず `hasOwnProperty` だけを見るので、`undefined` の
 * スロットは検査を通ったうえで `JSON.stringify` に落とされ、キーが黙って消えた
 * 要求になる。これだけは送る前に止める。
 *
 * `null` は止めない —— 正本は「`null` の値は S-2 として処理段階に渡り、内容の
 * 誤りとして扱われる」と定めている(sync-wire-schema/design.md:209)。
 *
 * Args:
 *     event: 完成形のイベント。
 *
 * Returns:
 *     `undefined` を持つスロット ID。無ければ undefined。
 */
function findUndefinedSlot(event: SyncEvent): string | undefined {
  for (const [slotId, value] of Object.entries(event.fields)) {
    if (value === undefined) {
      return slotId
    }
  }
  return undefined
}

// L-2(同 :88)。1 以上で 2^53 − 1 以下の整数。
function isD1(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1
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
    // 試合の食い違いと D4 の混在は別の規約(design.md:199 と :200)なので分ける。
    if (!Object.is(slot.game, request.gameId)) {
      return failure(SYNC_EVENT_SEND_FAILURE.GAME_ID_MISMATCH, {
        slotD1: slot.d1,
      })
    }
    if (!Object.is(slot.d4, first!.d4)) {
      return failure(SYNC_EVENT_SEND_FAILURE.MIXED_SCOPE, { slotD1: slot.d1 })
    }
    if (!isD1(slot.d1)) {
      return failure(SYNC_EVENT_SEND_FAILURE.INVALID_D1, { slotD1: slot.d1 })
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
    // A5 の適用はスロットの D5 で結合する(durableQueue の matchesA5Target)。
    // 送る D5 とずれると、サーバーが受理しても端末のスロットへ適用できない。
    if (!Object.is(event.fields[D5_SLOT_ID], slot.d5)) {
      return failure(SYNC_EVENT_SEND_FAILURE.D5_MISMATCH, { slotD1: slot.d1 })
    }

    const undefinedSlot = findUndefinedSlot(event)
    if (undefinedSlot !== undefined) {
      return failure(SYNC_EVENT_SEND_FAILURE.UNDEFINED_SLOT_VALUE, {
        slotD1: slot.d1,
        violation: { violation: 'invalid-fields', target: undefinedSlot },
      })
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
      {
        body: built,
        ...(request.syncCredentials === undefined
          ? {}
          : { syncCredentials: request.syncCredentials }),
      },
    )
    return { sent: true, requestBody: built, response }
  } catch (error) {
    // 応答が返った失敗(S-1 違反の 422 を含む)と、応答が返らなかった失敗を
    // 分ける。正本は前者を「顕在化する」と定める(design.md:110・:281)。
    // 同じ理由へ畳むと、恒久的に失敗する要求を通信断と同じ見え方で回し続ける。
    if (error instanceof ApiError) {
      return failure(SYNC_EVENT_SEND_FAILURE.RESPONSE_NOT_INTERPRETED, {
        status: error.status,
        error,
      })
    }
    return failure(SYNC_EVENT_SEND_FAILURE.NO_RESPONSE, { error })
  }
}

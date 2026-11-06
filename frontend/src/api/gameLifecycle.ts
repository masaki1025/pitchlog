// 終了/追記再開の閉 transport。
//
// 読取は docs/features/mvp-lifecycle-ui/plan.md と
// MINIMUM-INTERFACE.md（lifecycle-prefix-v1）だけを扱う。旧DTOから finished や
// active 版・receipt を推測しない。書込は既存 `buildSyncEventRequestBody` の
// 入力検査を通したうえで、この2操作だけ `event_kind` の ordinal ID を wire の
// literal へ正規写像する。任意の event_kind 書換えや一般 raw 送信は作らない。
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import type { EventKind } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'
import type { SyncEventViolation } from '../lib/sync/validateSyncEvent'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import { ApiError, apiRequest, type SyncRequestCredentials } from './client'
import {
  buildSyncEventRequestBody,
  SYNC_EVENT_SEND_FAILURE,
  type SyncEventSendFailure,
} from './client.syncEvents'
import { canonicalUuid } from './authIntent'
import { isNativeUndoGame, type NativeUndoGame } from './nativeUndoGame'

/** 要求する projection。旧projectionはこのunitの成功に数えない。 */
export const GAME_LIFECYCLE_PROJECTION = 'lifecycle-prefix-v1' as const
/** 読取packetのprofile。 */
export const GAME_LIFECYCLE_READ_PROFILE = 'nonplay-prefix-read-v1' as const
/** lifecycle metadataのformatVersion。 */
export const GAME_LIFECYCLE_READ_FORMAT =
  'native-game-lifecycle-read-v1' as const
/** 書込payloadのformatVersion。 */
export const GAME_LIFECYCLE_PAYLOAD_FORMAT = 'native-game-lifecycle-v1' as const

export type GameLifecycleStatus = 'in_progress' | 'finished'
export type GameLifecycleAction = 'end' | 'reopen'

/** 終了確定版の表示pointer。値だけでは認可/保存資格にならない。 */
export type GameLifecycleTarget = Readonly<{
  version: string
  eventId: string
  receiptId: string
}>

export type GameLifecycleMeta = Readonly<{
  formatVersion: typeof GAME_LIFECYCLE_READ_FORMAT
  status: GameLifecycleStatus
  lastVersion: string
  active: GameLifecycleTarget | null
  activeStatsVersionId: string | null
}>

/**
 * lifecycle-prefix-v1 の読取値。
 *
 * NP prefix read の閉じた形に、このprojectionだけが返す status/lifecycle を
 * 足したもの。`after` はサーバーの実現在状態であり、`state`(開始時before)と
 * 取り違えない。
 */
export type GameLifecycleGame = Omit<NativeUndoGame, 'status'> &
  Readonly<{
    status: GameLifecycleStatus
    lifecycle: GameLifecycleMeta
  }>

export type GameLifecycleReadResult =
  | Readonly<{ kind: 'found'; game: GameLifecycleGame }>
  | Readonly<{ kind: 'not-found' }>
  | Readonly<{ kind: 'unavailable' }>
  | Readonly<{ kind: 'unsupported' }>

export type GameLifecycleWirePayload = Readonly<{
  formatVersion: typeof GAME_LIFECYCLE_PAYLOAD_FORMAT
  action: GameLifecycleAction
  checkpointRef: Readonly<{ id: string; revision: string; digest: string }>
  target: GameLifecycleTarget | null
  event: Readonly<{ eventId: string; receiptId: string }>
}>

export type GameLifecycleRequestBody = Readonly<{
  recording_right_proof: string
  events: readonly Readonly<Record<string, unknown>>[]
}>

/** このunitが追加する送信失敗。既存の失敗語彙はそのまま使う。 */
export const GAME_LIFECYCLE_SEND_FAILURE = {
  /** 再開種別が正本の写しに無い（root追補待ち）。 */
  EVENT_KIND_UNAVAILABLE: 'event-kind-unavailable',
  /** スロットの種別が要求した操作と食い違う。 */
  KIND_MISMATCH: 'kind-mismatch',
  /** 1要求1イベントでない。 */
  NOT_SINGLE_EVENT: 'not-single-event',
  /** wire本文がこの2操作の閉形と食い違う。 */
  EVENT_SHAPE_MISMATCH: 'event-shape-mismatch',
} as const

export type GameLifecycleSendFailure =
  | SyncEventSendFailure
  | (typeof GAME_LIFECYCLE_SEND_FAILURE)[keyof typeof GAME_LIFECYCLE_SEND_FAILURE]

export type GameLifecycleSendResult =
  | Readonly<{
      sent: true
      requestBody: GameLifecycleRequestBody
      response: unknown
    }>
  | Readonly<{
      sent: false
      reason: GameLifecycleSendFailure
      violation?: SyncEventViolation
      slotD1?: number
      /** 応答が返った場合の状態コード。 */
      status?: number
      error?: unknown
    }>

export type GameLifecycleRequestBodyResult =
  | Readonly<{ ok: true; body: GameLifecycleRequestBody }>
  | Readonly<{
      ok: false
      reason: GameLifecycleSendFailure
      violation?: SyncEventViolation
      slotD1?: number
    }>

/** 種別名は正本の写しにだけ置く。値の追加は正本の改訂で行う。 */
export const GAME_LIFECYCLE_EVENT_KIND_NAME = {
  end: '試合終了宣言',
  reopen: '試合再開',
} as const satisfies Readonly<Record<GameLifecycleAction, string>>

/** backend V5 が要求する literal。ordinal ID はここでだけ写像する。 */
export const GAME_LIFECYCLE_WIRE_EVENT_KIND = {
  end: 'game_end_declaration',
  reopen: 'game_reopen',
} as const satisfies Readonly<Record<GameLifecycleAction, string>>

export class GameLifecycleWireError extends Error {
  readonly code: string

  constructor(code: string) {
    super(`終了再開の要求を形成できません: ${code}`)
    this.name = 'GameLifecycleWireError'
    this.code = code
  }
}

type Json = Record<string, unknown>

function object(value: unknown): Json | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Json)
    : null
}

function exact(value: unknown, keys: readonly string[]): value is Json {
  const row = object(value)
  return (
    row !== null &&
    Object.keys(row).length === keys.length &&
    keys.every((key) => Object.hasOwn(row, key))
  )
}

function uuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length === 36 &&
    canonicalUuid.test(value)
  )
}

/** 0以上の十進文字列（leading zero なし）。 */
function decimal(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    /^(?:0|[1-9][0-9]*)$/.test(value)
  )
}

/** 1以上の十進文字列（leading zero なし）。 */
function positiveDecimal(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    /^[1-9][0-9]*$/.test(value)
  )
}

function digest(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value)
}

function isStatus(value: unknown): value is GameLifecycleStatus {
  return value === 'in_progress' || value === 'finished'
}

/** lifecycle metadataの閉検査。statusとの一致とfinishedの版同時性を要求する。 */
export function isGameLifecycleMeta(
  value: unknown,
  status: GameLifecycleStatus,
): value is GameLifecycleMeta {
  if (
    !exact(value, [
      'formatVersion',
      'status',
      'lastVersion',
      'active',
      'activeStatsVersionId',
    ]) ||
    value.formatVersion !== GAME_LIFECYCLE_READ_FORMAT ||
    value.status !== status ||
    !decimal(value.lastVersion)
  )
    return false
  if (value.active === null) {
    return status === 'in_progress' && value.activeStatsVersionId === null
  }
  return (
    status === 'finished' &&
    exact(value.active, ['version', 'eventId', 'receiptId']) &&
    positiveDecimal(value.active.version) &&
    uuid(value.active.eventId) &&
    uuid(value.active.receiptId) &&
    value.active.version === value.lastVersion &&
    uuid(value.activeStatsVersionId)
  )
}

/**
 * lifecycle-prefix-v1 の応答か。
 *
 * NP read の全構造は既存 `isNativeUndoGame` に委ね、ここでは lifecycle 固有の
 * status/metadata だけを足す。既存検査は status='in_progress' を要求するため、
 * 複製せず status だけ差し替えて再利用する（finished を in_progress と混同しない）。
 */
export function isGameLifecycleGame(
  value: unknown,
): value is GameLifecycleGame {
  const row = object(value)
  if (row === null || !isStatus(row.status)) return false
  const { status, lifecycle, ...prefix } = row
  if (!isNativeUndoGame({ ...prefix, status: 'in_progress' })) return false
  return isGameLifecycleMeta(lifecycle, status)
}

/**
 * 読取を1回だけ行う。旧projection/旧DTO/不完全応答は成功にしない。
 *
 * Args:
 *     id: 試合ID。
 *     options: cursor（省略可）、limit、中断signal。
 *
 * Returns:
 *     found / not-found / unavailable / unsupported のいずれか。
 */
export async function readGameLifecycle(
  id: string,
  options: Readonly<{
    cursor?: string | null
    limit?: number
    signal?: AbortSignal
  }> = {},
): Promise<GameLifecycleReadResult> {
  const limit = options.limit ?? 25
  const cursor = options.cursor ?? null
  if (
    !uuid(id) ||
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    !(
      cursor === null ||
      (typeof cursor === 'string' &&
        cursor.length >= 1 &&
        cursor.length <= 2048 &&
        !/[\u0000-\u001f\u007f]/.test(cursor))
    )
  )
    throw new Error('終了再開の読取条件が正しくありません')

  let value: unknown
  try {
    value = await apiRequest<unknown>('GET', `/games/${id}/started`, {
      tenantBound: true,
      query: {
        projection: GAME_LIFECYCLE_PROJECTION,
        limit,
        ...(cursor === null ? {} : { cursor }),
      },
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) return { kind: 'not-found' }
      if (error.status === 409) return { kind: 'unavailable' }
      if ([400, 422, 501].includes(error.status)) return { kind: 'unsupported' }
    }
    throw error
  }

  if (
    isGameLifecycleGame(value) &&
    value.id === id &&
    value.profile === GAME_LIFECYCLE_READ_PROFILE &&
    value.page.items.length <= limit &&
    (value.page.next_cursor === null || value.page.next_cursor !== cursor)
  )
    return { kind: 'found', game: value }
  // 旧serverがNP prefixを返しても、lifecycle metadataの無い成功へ昇格しない。
  if (isNativeUndoGame(value) && value.id === id) return { kind: 'unsupported' }
  throw new Error('終了再開の応答を確認できません')
}

/**
 * 正本の写しから操作の種別を引く。再開は未裁定の間 undefined を返す。
 *
 * Args:
 *     action: 終了または追記再開。
 *
 * Returns:
 *     正本の写しにある種別。無ければ undefined（castしない）。
 */
export function gameLifecycleEventKind(
  action: GameLifecycleAction,
): EventKind | undefined {
  const name = GAME_LIFECYCLE_EVENT_KIND_NAME[action]
  return EVENT_KIND_RULES.find((rule) => rule.name === name)
}

/**
 * V7 payloadを閉じた形で組み立てる。
 *
 * Args:
 *     input: 操作・CP参照・再開対象・予約ID。
 *
 * Returns:
 *     正規化した payload。
 *
 * Raises:
 *     GameLifecycleWireError: 形が閉じない場合。
 */
export function buildGameLifecyclePayload(
  input: Readonly<{
    action: GameLifecycleAction
    checkpointRef: Readonly<{ id: string; revision: string; digest: string }>
    target: GameLifecycleTarget | null
    event: Readonly<{ eventId: string; receiptId: string }>
  }>,
): GameLifecycleWirePayload {
  if (
    !exact(input.checkpointRef, ['id', 'revision', 'digest']) ||
    !uuid(input.checkpointRef.id) ||
    !positiveDecimal(input.checkpointRef.revision) ||
    !digest(input.checkpointRef.digest) ||
    !exact(input.event, ['eventId', 'receiptId']) ||
    !uuid(input.event.eventId) ||
    !uuid(input.event.receiptId)
  )
    throw new GameLifecycleWireError('invalid-reference')
  if (input.action === 'end') {
    if (input.target !== null) throw new GameLifecycleWireError('end-target')
  } else if (
    !exact(input.target, ['version', 'eventId', 'receiptId']) ||
    !positiveDecimal(input.target.version) ||
    !uuid(input.target.eventId) ||
    !uuid(input.target.receiptId)
  )
    throw new GameLifecycleWireError('reopen-target')
  return {
    formatVersion: GAME_LIFECYCLE_PAYLOAD_FORMAT,
    action: input.action,
    checkpointRef: { ...input.checkpointRef },
    target:
      input.action === 'end'
        ? null
        : {
            version: input.target!.version,
            eventId: input.target!.eventId,
            receiptId: input.target!.receiptId,
          },
    event: { ...input.event },
  }
}

/**
 * スロットへ載せるイベントを閉じた形で組み立てる。
 *
 * V1/V3/V4/V5/V6/V7 を持つ。D1(V2)はキュー採番後に送信直前に束縛されるため
 * ここでは持たない（既存 `buildSyncEventRequestBody` と同じ規律）。V6は
 * サーバー由来の next_position.d2 であり、物理play番号やactiveDepthと混同しない。
 *
 * Args:
 *     input: 試合・D4・D5・D2・payload・種別。
 *
 * Returns:
 *     正本のフィールド写しに沿ったイベント。
 */
export function buildGameLifecycleSyncEvent(
  input: Readonly<{
    gameId: string
    d4: string
    d5: string
    d2: number
    payload: GameLifecycleWirePayload
    eventKind: EventKind
  }>,
): SyncEvent {
  if (
    !uuid(input.gameId) ||
    typeof input.d4 !== 'string' ||
    input.d4.length < 1 ||
    input.d4.length > 128 ||
    !uuid(input.d5) ||
    !Number.isSafeInteger(input.d2) ||
    input.d2 < 0
  )
    throw new GameLifecycleWireError('invalid-event')
  return {
    fields: {
      V1: input.d5,
      V3: input.d4,
      V4: input.gameId,
      V5: input.eventKind.id,
      V6: input.d2,
      V7: input.payload,
    },
  }
}

function isLifecycleWireEvent(value: unknown): boolean {
  return (
    exact(value, [
      'd5',
      'd1',
      'd4',
      'game_id',
      'event_kind',
      'd2',
      'payload',
    ]) &&
    uuid(value.d5) &&
    Number.isSafeInteger(value.d1) &&
    (value.d1 as number) >= 1 &&
    typeof value.d4 === 'string' &&
    uuid(value.game_id) &&
    Number.isSafeInteger(value.d2) &&
    (value.d2 as number) >= 0 &&
    isGameLifecyclePayloadObject(value.payload)
  )
}

/** 送信/再送する本文か。保存済み本文の再送前に必ず通す。 */
export function isGameLifecycleRequestBody(
  value: unknown,
): value is GameLifecycleRequestBody {
  if (!exact(value, ['recording_right_proof', 'events'])) return false
  if (
    typeof value.recording_right_proof !== 'string' ||
    value.recording_right_proof.length === 0
  )
    return false
  if (!Array.isArray(value.events) || value.events.length !== 1) return false
  const event = value.events[0]
  if (!isLifecycleWireEvent(event)) return false
  return (
    Object.values(GAME_LIFECYCLE_WIRE_EVENT_KIND) as readonly string[]
  ).includes(event.event_kind as string)
}

function isGameLifecyclePayloadObject(value: unknown): boolean {
  if (
    !exact(value, [
      'formatVersion',
      'action',
      'checkpointRef',
      'target',
      'event',
    ])
  )
    return false
  if (
    value.formatVersion !== GAME_LIFECYCLE_PAYLOAD_FORMAT ||
    (value.action !== 'end' && value.action !== 'reopen')
  )
    return false
  try {
    buildGameLifecyclePayload({
      action: value.action,
      checkpointRef:
        value.checkpointRef as GameLifecycleWirePayload['checkpointRef'],
      target: value.target as GameLifecycleTarget | null,
      event: value.event as GameLifecycleWirePayload['event'],
    })
    return true
  } catch {
    return false
  }
}

/**
 * 既存検査を通したうえで、この2操作だけ event_kind を wire literal へ写す。
 *
 * Args:
 *     input: 試合・V12・スロット・操作・正本の種別。
 *
 * Returns:
 *     送信本文、または既存検査/写像の失敗。
 */
export function buildGameLifecycleRequestBody(
  input: Readonly<{
    gameId: string
    recordingRightProof: unknown
    slot: DurableQueueSlot
    action: GameLifecycleAction
    eventKind: EventKind
  }>,
): GameLifecycleRequestBodyResult {
  if (input.eventKind.name !== GAME_LIFECYCLE_EVENT_KIND_NAME[input.action])
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.KIND_MISMATCH,
      slotD1: input.slot.d1,
    }
  if (!Object.is(input.slot.event.fields.V5, input.eventKind.id))
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.KIND_MISMATCH,
      slotD1: input.slot.d1,
    }
  const built = buildSyncEventRequestBody({
    gameId: input.gameId,
    recordingRightProof: input.recordingRightProof,
    slots: [input.slot],
    eventKinds: [input.eventKind],
  })
  if ('sent' in built) {
    if (built.sent)
      return {
        ok: false,
        reason: GAME_LIFECYCLE_SEND_FAILURE.NOT_SINGLE_EVENT,
        slotD1: input.slot.d1,
      }
    return {
      ok: false,
      reason: built.reason,
      ...(built.violation === undefined ? {} : { violation: built.violation }),
      ...(built.slotD1 === undefined ? {} : { slotD1: built.slotD1 }),
    }
  }
  if (
    typeof built.recording_right_proof !== 'string' ||
    built.recording_right_proof.length === 0
  )
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.EVENT_SHAPE_MISMATCH,
      slotD1: input.slot.d1,
    }
  const events = built.events
  if (events.length !== 1)
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.NOT_SINGLE_EVENT,
      slotD1: input.slot.d1,
    }
  const [event] = events
  if (event.event_kind !== input.eventKind.id)
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.KIND_MISMATCH,
      slotD1: input.slot.d1,
    }
  if (
    !isLifecycleWireEvent(event) ||
    Object.is(event.d5, undefined) ||
    !Object.is(event.d5, input.slot.d5) ||
    !Object.is(event.d4, input.slot.d4) ||
    !Object.is(event.game_id, input.gameId) ||
    !Object.is(event.d1, input.slot.d1) ||
    !isGameLifecyclePayloadObject(event.payload)
  )
    return {
      ok: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.EVENT_SHAPE_MISMATCH,
      slotD1: input.slot.d1,
    }
  const body: GameLifecycleRequestBody = {
    recording_right_proof: built.recording_right_proof,
    events: [
      Object.freeze({
        ...event,
        event_kind: GAME_LIFECYCLE_WIRE_EVENT_KIND[input.action],
      }),
    ],
  }
  return isGameLifecycleRequestBody(body)
    ? { ok: true, body }
    : {
        ok: false,
        reason: GAME_LIFECYCLE_SEND_FAILURE.EVENT_SHAPE_MISMATCH,
        slotD1: input.slot.d1,
      }
}

/**
 * 保存済み本文をそのまま送る。本文は呼出元が耐久storeから復元したもの。
 *
 * Args:
 *     gameId: path の試合ID。
 *     body: V12込みの完成本文。
 *     credentials: 実端末資格と耐久attempt。
 *
 * Returns:
 *     送信の可否と応答、または失敗理由。
 */
export async function postGameLifecycleRequestBody(
  gameId: string,
  body: GameLifecycleRequestBody,
  credentials?: SyncRequestCredentials,
): Promise<GameLifecycleSendResult> {
  if (!isGameLifecycleRequestBody(body))
    return {
      sent: false,
      reason: GAME_LIFECYCLE_SEND_FAILURE.EVENT_SHAPE_MISMATCH,
    }
  try {
    const response = await apiRequest<unknown>(
      'POST',
      `/games/${encodeURIComponent(gameId)}/sync/events`,
      {
        body,
        ...(credentials === undefined ? {} : { syncCredentials: credentials }),
      },
    )
    return { sent: true, requestBody: body, response }
  } catch (error) {
    if (error instanceof ApiError) {
      return {
        sent: false,
        reason: SYNC_EVENT_SEND_FAILURE.RESPONSE_NOT_INTERPRETED,
        status: error.status,
        error,
      }
    }
    return { sent: false, reason: SYNC_EVENT_SEND_FAILURE.NO_RESPONSE, error }
  }
}

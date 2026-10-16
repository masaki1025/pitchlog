// 1 球(毎球入力)の確定値から同期イベントの「下書き」を組み立てる純関数。
//
// 下書きは D1(V2)と状態差分(V8)を持たない。D1 は端末の永続キューへの追記
// トランザクションの中で採番され(frontend/src/lib/sync/durableQueue.ts)、状態差分の
// 供給元は状況計算核(U-X1)であり、本計画の第 1 期では用意できないためである
// (docs/features/uf8-game-recording/design.md 2 節・4-1' 節)。
//
// スロットの要否の正は docs/design/sync-protocol.md 4-3 で、その写しが
// frontend/src/lib/sync/eventFieldRules.ts にある。本モジュールは要否を書き写さず、
// 同表の判定(resolveEventFieldPresence)から導く(NFR-018)。
import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_RULES,
  EVENT_KIND_SLOT_ID,
  EVENT_SLOT_IDS,
  isCancellableEventKind,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
  type EventFieldConditionContext,
  type EventSlotId,
  type SyncEventPath,
} from '../lib/sync/eventFieldRules'
import { EVENT_KIND_RULES, type EventKind } from '../lib/sync/eventKinds'

// スロットと wire のキーの対応は docs/features/sync-wire-schema/design.md 3-2 の表が正
// (d5=V1 / d1=V2 / d4=V3 / game_id=V4 / event_kind=V5 / d2=V6 / payload=V7 /
// state_diff=V8)。ここは対応の宣言であって、要否の規則ではない。
const D5_SLOT_ID = 'V1' satisfies EventSlotId
const D1_SLOT_ID = 'V2' satisfies EventSlotId
const D4_SLOT_ID = 'V3' satisfies EventSlotId
const GAME_ID_SLOT_ID = 'V4' satisfies EventSlotId
const D2_SLOT_ID = 'V6' satisfies EventSlotId
const PAYLOAD_SLOT_ID = 'V7' satisfies EventSlotId
const STATE_DIFF_SLOT_ID = 'V8' satisfies EventSlotId

/** 1 球の記録が通る経路。経路はクライアントが選ばず正本 8-1 の経路表に従う。 */
export const PITCH_EVENT_PATH: SyncEventPath = SYNC_EVENT_PATH.P2

/** 毎球入力の種別。正本 5-5 の写し(eventKinds.ts)から引く。 */
export const PITCH_EVENT_KIND: EventKind = (() => {
  const kind = EVENT_KIND_RULES.find((rule) => rule.name === '毎球入力')
  if (!kind) {
    throw new Error('毎球入力の種別が正本の写しにありません')
  }
  return kind
})()

const PITCH_EVENT_FIELD_CONTEXT: EventFieldConditionContext = {
  path: PITCH_EVENT_PATH,
  eventKind: PITCH_EVENT_KIND,
  participation: PITCH_EVENT_KIND.participation,
  cancellable: isCancellableEventKind(PITCH_EVENT_KIND),
}

const EVENT_SLOT_ID_SET = new Set<string>(EVENT_SLOT_IDS)

/** 1 球の記録で必須になるスロット(正本の要否判定から導く)。 */
export const PITCH_EVENT_REQUIRED_SLOT_IDS: readonly EventSlotId[] =
  Object.freeze(
    EVENT_FIELD_RULES.filter(
      (rule) =>
        EVENT_SLOT_ID_SET.has(rule.id) &&
        resolveEventFieldPresence(rule, PITCH_EVENT_FIELD_CONTEXT) ===
          EVENT_FIELD_PRESENCE.REQUIRED,
    ).map((rule) => rule.id as EventSlotId),
  )

/** 下書きの段階では埋められないスロット(採番前の D1 と、計算核が供給する状態差分)。 */
export const PITCH_EVENT_DEFERRED_SLOT_IDS: readonly EventSlotId[] =
  Object.freeze([D1_SLOT_ID, STATE_DIFF_SLOT_ID])

const DEFERRED_SLOT_ID_SET = new Set<string>(PITCH_EVENT_DEFERRED_SLOT_IDS)

/** 下書きが運ぶスロット = 必須スロット − 繰り延べたスロット。 */
export const PITCH_EVENT_DRAFT_SLOT_IDS: readonly EventSlotId[] = Object.freeze(
  PITCH_EVENT_REQUIRED_SLOT_IDS.filter((id) => !DEFERRED_SLOT_ID_SET.has(id)),
)

export const PITCH_EVENT_DRAFT_VIOLATION = {
  INVALID_D5: 'invalid-d5',
  INVALID_D4: 'invalid-d4',
  INVALID_GAME_ID: 'invalid-game-id',
  MISSING_D2: 'missing-d2',
  INVALID_PAYLOAD: 'invalid-payload',
  SLOT_SET_MISMATCH: 'slot-set-mismatch',
} as const

export type PitchEventDraftViolationType =
  (typeof PITCH_EVENT_DRAFT_VIOLATION)[keyof typeof PITCH_EVENT_DRAFT_VIOLATION]

export type PitchEventDraftViolation = {
  violation: PitchEventDraftViolationType
  target: string
}

export type PitchEventDraftInput = {
  /** D5(V1)。採番の所有者が未定のため、呼出元が与える値をそのまま使う。 */
  d5: string
  /** D4(V3)。クライアントが解釈しない不透明な文字列。 */
  d4: string
  /** 試合の識別(V4)。 */
  gameId: string
  /** D2(V6)。物理形式は正本が決めていない(論点 26)ので、値を解釈しない。 */
  d2: unknown
  /** 種別ごとの中身(V7)。本計画では中身を決めない。 */
  payload: Record<string, unknown>
}

export type PitchEventDraft = {
  readonly fields: Readonly<Partial<Record<EventSlotId, unknown>>>
}

export type PitchEventDraftResult =
  | { ok: true; draft: PitchEventDraft }
  | { ok: false; reason: PitchEventDraftViolation }

// L-1(docs/features/sync-wire-schema/design.md:87)。クライアントは正規形で送る。
const CANONICAL_UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function isCanonicalUuid(value: unknown): value is string {
  return typeof value === 'string' && CANONICAL_UUID_PATTERN.test(value)
}

// L-3。空文字は不可で、クライアントは分解・比較・生成をしない。
function isOpaqueString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isJsonObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  const prototype = Reflect.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    return false
  }
  return Reflect.ownKeys(value).every((key) => typeof key === 'string')
}

function failure(
  violation: PitchEventDraftViolationType,
  target: string,
): PitchEventDraftResult {
  return { ok: false, reason: { violation, target } }
}

/**
 * 1 球の確定値から同期イベントの下書きを組み立てる。
 *
 * 状況の計算は一切しない(カウントの楽観更新も含めない)。下書きは D1 と状態差分を
 * 持たないので、この戻り値だけで確定はできない。
 *
 * Args:
 *     input: 1 球の確定値。
 *
 * Returns:
 *     組み立てた下書き、または組み立てられない理由。
 */
export function buildPitchEventDraft(
  input: PitchEventDraftInput,
): PitchEventDraftResult {
  if (!isCanonicalUuid(input.d5)) {
    return failure(PITCH_EVENT_DRAFT_VIOLATION.INVALID_D5, 'd5')
  }
  if (!isOpaqueString(input.d4)) {
    return failure(PITCH_EVENT_DRAFT_VIOLATION.INVALID_D4, 'd4')
  }
  if (!isCanonicalUuid(input.gameId)) {
    return failure(PITCH_EVENT_DRAFT_VIOLATION.INVALID_GAME_ID, 'game_id')
  }
  if (input.d2 === undefined || input.d2 === null) {
    return failure(PITCH_EVENT_DRAFT_VIOLATION.MISSING_D2, 'd2')
  }
  if (!isJsonObject(input.payload)) {
    return failure(PITCH_EVENT_DRAFT_VIOLATION.INVALID_PAYLOAD, 'payload')
  }

  const fields: Partial<Record<EventSlotId, unknown>> = {
    [D5_SLOT_ID]: input.d5,
    [D4_SLOT_ID]: input.d4,
    [GAME_ID_SLOT_ID]: input.gameId,
    [EVENT_KIND_SLOT_ID]: PITCH_EVENT_KIND.id,
    [D2_SLOT_ID]: input.d2,
    // 呼出元が後から書き換えても下書きが変わらないよう、浅い複製を持つ。
    [PAYLOAD_SLOT_ID]: Object.freeze({ ...input.payload }),
  }

  // 正本の要否が変わったときに、古い形の下書きを黙って作り続けないための突合。
  const built = Object.keys(fields).sort()
  const expected = [...PITCH_EVENT_DRAFT_SLOT_IDS].sort()
  if (
    built.length !== expected.length ||
    built.some((slotId, index) => slotId !== expected[index])
  ) {
    return failure(
      PITCH_EVENT_DRAFT_VIOLATION.SLOT_SET_MISMATCH,
      built.join(','),
    )
  }

  return { ok: true, draft: Object.freeze({ fields: Object.freeze(fields) }) }
}

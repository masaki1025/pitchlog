// この判定は docs/design/sync-protocol.md 4-5 の D5 再利用禁止範囲と衝突規則の写しである。
// 射程は DI2・DI3・I2・I3 と内容同一性を判定できない場合の後着拒否に限る。
// DI1・DI5・I1・B3a は6章の処理段階に依存するため実装しない。

import { SYNC_EVENT_PATH, type SyncEventPath } from './eventFieldRules'
import type { SyncEvent } from './syncEvent'

export const CONTENT_IDENTITY = {
  SAME: 'same',
  DIFFERENT: 'different',
  INDETERMINATE: 'indeterminate',
} as const

export type ContentIdentity =
  (typeof CONTENT_IDENTITY)[keyof typeof CONTENT_IDENTITY]

export type IdempotencyEventOriginal = Readonly<{
  fields: Readonly<SyncEvent['fields']>
}>

export type IdempotencyOriginal = Readonly<{
  game: unknown
  recordingRightsGeneration: unknown
  path: SyncEventPath
  event: IdempotencyEventOriginal
}>

export type IdempotencyOriginalComparator = (
  firstOriginal: IdempotencyOriginal,
  laterOriginal: IdempotencyOriginal,
) => ContentIdentity

export const IDEMPOTENCY_DECISION = {
  NOT_DUPLICATE: '重複ではない',
  REPLAY_SAVED_RESULT: '保存済み結果の再掲',
  D1_COLLISION: 'B3b',
  P3_COLLISION: 'B13',
  REJECT_LATER: '後着拒否',
} as const

export type IdempotencyBoundaryResult =
  | typeof IDEMPOTENCY_DECISION.D1_COLLISION
  | typeof IDEMPOTENCY_DECISION.P3_COLLISION

export type IdempotencyKeyPart = 'tenant' | 'd5'

export type IdempotencyScopeRule = Readonly<{
  keyParts: readonly IdempotencyKeyPart[]
  differentTenantIsDuplicate: boolean
}>

export const IDEMPOTENCY_SCOPE_RULE: IdempotencyScopeRule = Object.freeze({
  keyParts: Object.freeze(['tenant', 'd5'] as const),
  differentTenantIsDuplicate: false,
})

type CollisionPathGroup = 'D1付き経路' | 'P3'

type CollisionRuleDefinition = Readonly<{
  id: 'DI2' | 'DI3' | 'I2' | 'I3'
  pathGroup: CollisionPathGroup
  contentIdentity:
    typeof CONTENT_IDENTITY.SAME | typeof CONTENT_IDENTITY.DIFFERENT
  rightHandSide: string
  effect:
    | Readonly<{ kind: 'replay' }>
    | Readonly<{
        kind: 'collision'
        result: IdempotencyBoundaryResult
      }>
}>

export const IDEMPOTENCY_COLLISION_RULES = [
  {
    id: 'DI2',
    pathGroup: 'D1付き経路',
    contentIdentity: CONTENT_IDENTITY.SAME,
    rightHandSide: '保存済み結果を再掲+再適用しない',
    effect: { kind: 'replay' },
  },
  {
    id: 'DI3',
    pathGroup: 'D1付き経路',
    contentIdentity: CONTENT_IDENTITY.DIFFERENT,
    rightHandSide: IDEMPOTENCY_DECISION.D1_COLLISION,
    effect: {
      kind: 'collision',
      result: IDEMPOTENCY_DECISION.D1_COLLISION,
    },
  },
  {
    id: 'I2',
    pathGroup: 'P3',
    contentIdentity: CONTENT_IDENTITY.SAME,
    rightHandSide: '保存済み結果を再掲+再適用しない',
    effect: { kind: 'replay' },
  },
  {
    id: 'I3',
    pathGroup: 'P3',
    contentIdentity: CONTENT_IDENTITY.DIFFERENT,
    rightHandSide: IDEMPOTENCY_DECISION.P3_COLLISION,
    effect: {
      kind: 'collision',
      result: IDEMPOTENCY_DECISION.P3_COLLISION,
    },
  },
] as const satisfies readonly CollisionRuleDefinition[]

export type IdempotencyOperation = Readonly<{
  tenant: unknown
  d5: unknown
  original: IdempotencyOriginal
}>

export type StoredIdempotencyOperation<SavedResult> = Readonly<{
  operation: IdempotencyOperation
  savedResult: SavedResult
}>

export type IdempotencyDecisionResult<SavedResult> =
  | Readonly<{ decision: typeof IDEMPOTENCY_DECISION.NOT_DUPLICATE }>
  | Readonly<{
      decision: typeof IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT
      savedResult: SavedResult
    }>
  | Readonly<{
      decision: IdempotencyBoundaryResult
    }>
  | Readonly<{
      decision: typeof IDEMPOTENCY_DECISION.REJECT_LATER
    }>

function isSameIdempotencyKey(
  first: IdempotencyOperation,
  later: IdempotencyOperation,
): boolean {
  const sameTenant = Object.is(first.tenant, later.tenant)
  if (!sameTenant && !IDEMPOTENCY_SCOPE_RULE.differentTenantIsDuplicate) {
    return false
  }

  if (!sameTenant) {
    return Object.is(first.d5, later.d5)
  }

  return IDEMPOTENCY_SCOPE_RULE.keyParts.every((part) =>
    Object.is(first[part], later[part]),
  )
}

function pathGroup(path: SyncEventPath): CollisionPathGroup {
  return path === SYNC_EVENT_PATH.P3 ? 'P3' : 'D1付き経路'
}

function rejectLater<SavedResult>(): IdempotencyDecisionResult<SavedResult> {
  return { decision: IDEMPOTENCY_DECISION.REJECT_LATER }
}

export function decideIdempotencyCollision<SavedResult>(
  later: IdempotencyOperation,
  storedOperations: readonly StoredIdempotencyOperation<SavedResult>[],
  compareOriginal: IdempotencyOriginalComparator,
): IdempotencyDecisionResult<SavedResult> {
  const matches = storedOperations.filter((stored) =>
    isSameIdempotencyKey(stored.operation, later),
  )

  if (matches.length === 0) {
    return { decision: IDEMPOTENCY_DECISION.NOT_DUPLICATE }
  }
  if (matches.length !== 1) {
    return rejectLater()
  }

  const first = matches[0]!
  let contentIdentity: ContentIdentity
  try {
    contentIdentity = compareOriginal(first.operation.original, later.original)
  } catch {
    return rejectLater()
  }

  if (contentIdentity === CONTENT_IDENTITY.INDETERMINATE) {
    return rejectLater()
  }

  const rule = IDEMPOTENCY_COLLISION_RULES.find(
    (candidate) =>
      candidate.pathGroup === pathGroup(later.original.path) &&
      candidate.contentIdentity === contentIdentity,
  )
  if (!rule) {
    return rejectLater()
  }

  if (rule.effect.kind === 'replay') {
    return {
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: first.savedResult,
    }
  }

  return { decision: rule.effect.result }
}

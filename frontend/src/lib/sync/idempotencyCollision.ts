// この判定は docs/design/sync-protocol.md 4-5 の D5 再利用禁止範囲と衝突規則の写しである。
// 射程は DI2・DI3・I2・I3、内容同一性の fail-closed 分類、B3b の分岐に限る。
// DI5 は混在バッチの A5 を扱い、B3a が T9 の永続化を伴うため TSK-330 の射程とする。

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

export type B3BranchRule = Readonly<{
  id: typeof IDEMPOTENCY_DECISION.D1_COLLISION
  name: string
  clauses: readonly [string, string, string]
  rightHandSide: string
  startsT9: false
}>

const b3ExistingD5BranchClauses = Object.freeze([
  '先着原本との比較',
  'B3',
  'T9開始なし',
] as const)

export const B3_EXISTING_D5_BRANCH_RULE: B3BranchRule = Object.freeze({
  id: IDEMPOTENCY_DECISION.D1_COLLISION,
  name: '既存D5との衝突',
  clauses: b3ExistingD5BranchClauses,
  rightHandSide: b3ExistingD5BranchClauses.join('+'),
  startsT9: false,
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

export class IdempotencyCollisionCorruptionError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'IdempotencyCollisionCorruptionError'
  }
}

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
  return Object.is(path, SYNC_EVENT_PATH.P3) ? 'P3' : 'D1付き経路'
}

export function decideIdempotencyCollision<SavedResult>(
  later: IdempotencyOperation,
  storedOperations: readonly StoredIdempotencyOperation<SavedResult>[],
  compareOriginal: IdempotencyOriginalComparator,
): IdempotencyDecisionResult<SavedResult> {
  const matches = Object.freeze(
    storedOperations.filter((stored) =>
      isSameIdempotencyKey(stored.operation, later),
    ),
  )

  if (matches.length === 0) {
    return { decision: IDEMPOTENCY_DECISION.NOT_DUPLICATE }
  }
  if (matches.length !== 1) {
    throw new IdempotencyCollisionCorruptionError(
      '同一の冪等キーに一意な先着原本がありません',
    )
  }

  const first = matches[0]!
  let contentIdentity: ContentIdentity
  try {
    contentIdentity = compareOriginal(first.operation.original, later.original)
  } catch {
    contentIdentity = CONTENT_IDENTITY.DIFFERENT
  }

  if (Object.is(contentIdentity, CONTENT_IDENTITY.INDETERMINATE)) {
    contentIdentity = CONTENT_IDENTITY.DIFFERENT
  }

  const laterPathGroup = pathGroup(later.original.path)
  const rule = IDEMPOTENCY_COLLISION_RULES.find(
    (candidate) =>
      Object.is(candidate.pathGroup, laterPathGroup) &&
      Object.is(candidate.contentIdentity, contentIdentity),
  )
  if (!rule) {
    throw new IdempotencyCollisionCorruptionError(
      `D5 衝突規則がありません: ${laterPathGroup}/${contentIdentity}`,
    )
  }

  if (!('result' in rule.effect)) {
    return {
      decision: IDEMPOTENCY_DECISION.REPLAY_SAVED_RESULT,
      savedResult: first.savedResult,
    }
  }

  return { decision: rule.effect.result }
}

// このパーサは docs/design/sync-protocol.md 4-3・4-4・4-5・5-5・7-2・8-1 の対象規則の写しである。
// 射程は source_elements の正本語彙と構造の読み取りに限り、値の変更は正本の改訂ゲートを通す。
// 同期処理の実行は各製品モジュールの責務であるため射程外とする。
// 正本語彙を必要とする同期モジュールとテストから使う。
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import { EVENT_KIND_RULES } from './eventKinds'

const EVENT_FIELD_RELATION_ID = 'R-EVENT-FIELD'
const EVENT_FIELD_ID_PATTERN = /^V\d+$/
const PARTICIPATION_RELATION_ID = 'R-PARTICIPATION'
const V12_BOUNDARY_RELATION_ID = 'R-V12-BOUNDARY'
const D1_BOUNDARY_RELATION_ID = 'R-BOUNDARY'
const P3_BOUNDARY_RELATION_ID = 'R-P3-BOUNDARY'
const TEMPORARY_ID_MAPPING_RELATION_ID = 'R-TEMP-ID-MAPPING'
const TXN_ROUTE_RELATION_ID = 'R-TXN-ROUTE'
const QUEUE_LIFE_RELATION_ID = 'R-QUEUE-LIFE'
const ACK_STATE_RELATION_ID = 'R-ACK-STATE'
const EVENT_KIND_IDS = new Set<string>(
  EVENT_KIND_RULES.map((eventKind) => eventKind.id),
)

type CanonEventFieldRequiredness =
  '全イベントで無条件' | '種別条件付き' | '要求レベル'
type CanonEventFieldShape =
  | { readonly kind: 'opaque' }
  | {
      readonly kind: 'composite'
      readonly elements: readonly ['試合', '対象の D4', '対象の D1']
    }

const OPAQUE_SHAPE = { kind: 'opaque' } as const
const TARGET_REFERENCE_SHAPE = {
  kind: 'composite',
  elements: ['試合', '対象の D4', '対象の D1'],
} as const

const SHAPE_BY_DESCRIPTION = new Map<string, CanonEventFieldShape>([
  ['べき等キーD5', OPAQUE_SHAPE],
  ['イベント連番D1', OPAQUE_SHAPE],
  ['記録権世代D4', OPAQUE_SHAPE],
  ['試合の識別', OPAQUE_SHAPE],
  ['イベント種別', OPAQUE_SHAPE],
  ['論理位置を定める値D2', OPAQUE_SHAPE],
  ['ペイロード', OPAQUE_SHAPE],
  ['状態差分', OPAQUE_SHAPE],
  ['置換・墓標の状態', OPAQUE_SHAPE],
  ['対象イベントの参照', TARGET_REFERENCE_SHAPE],
  ['対象の期待版', OPAQUE_SHAPE],
  ['記録権証明', OPAQUE_SHAPE],
])

const REQUIREDNESS_BY_TOKEN = new Map<string, CanonEventFieldRequiredness>([
  ['全イベントで無条件', '全イベントで無条件'],
  ['P1・P2・P4に必須', '種別条件付き'],
  ['P3は持たない', '種別条件付き'],
  ['P3は持たず', '種別条件付き'],
  ['種別条件付き', '種別条件付き'],
  ['P3自身は持たず', '種別条件付き'],
  ['取消可能な操作に限る', '種別条件付き'],
  ['墓標・改訂に限る', '種別条件付き'],
  ['P3は必須', '種別条件付き'],
  ['P3に必須', '種別条件付き'],
  ['要求レベル', '要求レベル'],
  ['P1・P2・P4', '要求レベル'],
  ['進行中のP3', '要求レベル'],
  ['終了後のP3には不要', '要求レベル'],
])

type CanonParticipation =
  '論理位置を持つ' | '同期順のみ' | '従属' | '元イベントの参加区分を継承'

const PARTICIPATIONS = new Set<CanonParticipation>([
  '論理位置を持つ',
  '同期順のみ',
  '従属',
  '元イベントの参加区分を継承',
])
const REVISION_ORDER_TOKEN = '変更版順'
const REVISION_ORDER_DEFINITION = {
  id: 'K4',
  name: '変更版順',
  tokens: ['D1・D2とは別で論理再生順に使わない'],
} as const
// K5 は種別集合には入らないが、墓標生成条件として専用 reader が読み取る。
const TOMBSTONE_RULE_DEFINITION = {
  id: 'K5',
  name: '墓標生成',
  tokens: ['オンライン記録権確認後', 'D1付きキュー'],
} as const

export type CanonEventFieldRule = {
  id: string
  requiredness: CanonEventFieldRequiredness
  conditions: readonly string[]
  shape: CanonEventFieldShape
}

export type CanonEventKindRule = {
  id: string
  name: string
  participation: CanonParticipation
  hasRevisionOrder: boolean
}

export type CanonTombstoneRule = Readonly<{
  id: typeof TOMBSTONE_RULE_DEFINITION.id
  name: typeof TOMBSTONE_RULE_DEFINITION.name
  tokens: typeof TOMBSTONE_RULE_DEFINITION.tokens
}>

type ParticipationSourceElement = {
  id: string
  name: string
  tokens: readonly string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseSourceElement(sourceElement: unknown): CanonEventFieldRule {
  if (typeof sourceElement !== 'string') {
    throw new Error('R-EVENT-FIELD の要素は文字列でなければなりません')
  }

  const parts = sourceElement.split(':')
  if (parts.length !== 2) {
    throw new Error(`R-EVENT-FIELD の要素形式が不正です: ${sourceElement}`)
  }

  const [id, body] = parts
  if (!id || !EVENT_FIELD_ID_PATTERN.test(id)) {
    throw new Error(`未知の正本 ID です: ${id ?? ''}`)
  }

  const [description, ...conditionTokens] = body?.split('+') ?? []
  const shape = description ? SHAPE_BY_DESCRIPTION.get(description) : undefined
  if (!shape) {
    throw new Error(`未知の正本語です: ${description ?? ''}`)
  }
  if (conditionTokens.length === 0) {
    throw new Error(`必須区分がありません: ${sourceElement}`)
  }

  const requirednesses = new Set<CanonEventFieldRequiredness>()
  for (const token of conditionTokens) {
    const requiredness = REQUIREDNESS_BY_TOKEN.get(token)
    if (!requiredness) {
      throw new Error(`未知の正本語です: ${token}`)
    }
    requirednesses.add(requiredness)
  }
  if (requirednesses.size !== 1) {
    throw new Error(`必須区分が一意に定まりません: ${sourceElement}`)
  }

  return Object.freeze({
    id,
    requiredness: [...requirednesses][0]!,
    conditions: Object.freeze(conditionTokens),
    shape,
  })
}

function parseParticipationSourceElement(
  sourceElement: unknown,
): ParticipationSourceElement {
  if (typeof sourceElement !== 'string') {
    throw new Error('R-PARTICIPATION の要素は文字列でなければなりません')
  }

  const idParts = sourceElement.split(':')
  if (idParts.length !== 2) {
    throw new Error(`R-PARTICIPATION の要素形式が不正です: ${sourceElement}`)
  }
  const [id, body] = idParts
  const bodyParts = body?.split('=') ?? []
  if (!id || bodyParts.length !== 2) {
    throw new Error(`R-PARTICIPATION の要素形式が不正です: ${sourceElement}`)
  }
  const [name, tokenBody] = bodyParts
  const tokens = tokenBody?.split('+') ?? []
  if (
    !name ||
    tokens.length === 0 ||
    tokens.some((token) => token.length === 0)
  ) {
    throw new Error(`R-PARTICIPATION の要素形式が不正です: ${sourceElement}`)
  }
  return { id, name, tokens }
}

function hasExactTokens(
  actual: readonly string[],
  expected: readonly string[],
): boolean {
  return (
    actual.length === expected.length &&
    actual.every((token, index) => token === expected[index])
  )
}

function assertParticipationDefinition(
  element: ParticipationSourceElement,
  expected: ParticipationSourceElement,
): void {
  if (
    element.name !== expected.name ||
    !hasExactTokens(element.tokens, expected.tokens)
  ) {
    throw new Error(`R-PARTICIPATION の定義が不正です: ${element.id}`)
  }
}

function parseEventKindParticipation(
  element: ParticipationSourceElement,
): CanonEventKindRule {
  if (!EVENT_KIND_IDS.has(element.id)) {
    throw new Error(`未知の R-PARTICIPATION ID です: ${element.id}`)
  }

  const participationTokens: CanonParticipation[] = []
  let hasRevisionOrder = false
  for (const token of element.tokens) {
    if (PARTICIPATIONS.has(token as CanonParticipation)) {
      participationTokens.push(token as CanonParticipation)
    } else if (token === REVISION_ORDER_TOKEN) {
      hasRevisionOrder = true
    } else {
      throw new Error(`未知の R-PARTICIPATION 語です: ${token}`)
    }
  }
  if (participationTokens.length !== 1) {
    throw new Error(`参加区分が一意に定まりません: ${element.id}`)
  }

  return Object.freeze({
    id: element.id,
    name: element.name,
    participation: participationTokens[0]!,
    hasRevisionOrder,
  })
}

export function parseCanonEventFieldRules(
  sourceElements: readonly unknown[],
): readonly CanonEventFieldRule[] {
  const rules = sourceElements.map(parseSourceElement)
  const ids = new Set(rules.map((rule) => rule.id))
  if (ids.size !== rules.length) {
    throw new Error('R-EVENT-FIELD に重複した正本 ID があります')
  }
  return Object.freeze(rules)
}

export function readCanonEventFieldRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonEventFieldRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[EVENT_FIELD_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-EVENT-FIELD.source_elements がありません')
  }
  return parseCanonEventFieldRules(relation.source_elements)
}

export function parseCanonParticipationRules(
  sourceElements: readonly unknown[],
): readonly CanonEventKindRule[] {
  const elements = sourceElements.map(parseParticipationSourceElement)
  const ids = new Set(elements.map((element) => element.id))
  if (ids.size !== elements.length) {
    throw new Error('R-PARTICIPATION に重複した ID があります')
  }

  let hasRevisionOrderDefinition = false
  let hasTombstoneRuleDefinition = false
  const eventKinds: CanonEventKindRule[] = []
  for (const element of elements) {
    if (element.id === REVISION_ORDER_DEFINITION.id) {
      assertParticipationDefinition(element, REVISION_ORDER_DEFINITION)
      hasRevisionOrderDefinition = true
    } else if (element.id === TOMBSTONE_RULE_DEFINITION.id) {
      assertParticipationDefinition(element, TOMBSTONE_RULE_DEFINITION)
      hasTombstoneRuleDefinition = true
    } else {
      eventKinds.push(parseEventKindParticipation(element))
    }
  }
  if (!hasRevisionOrderDefinition || !hasTombstoneRuleDefinition) {
    throw new Error('R-PARTICIPATION の定義行が不足しています')
  }
  return Object.freeze(eventKinds)
}

export function readCanonParticipationRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonEventKindRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[PARTICIPATION_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-PARTICIPATION.source_elements がありません')
  }
  return parseCanonParticipationRules(relation.source_elements)
}

export function parseCanonTombstoneRule(
  sourceElements: readonly unknown[],
): CanonTombstoneRule {
  const tombstoneElements = sourceElements
    .map(parseParticipationSourceElement)
    .filter((element) => element.id === TOMBSTONE_RULE_DEFINITION.id)

  if (tombstoneElements.length !== 1) {
    throw new Error('R-PARTICIPATION の K5 行が一意ではありません')
  }

  const tombstoneElement = tombstoneElements[0]!
  assertParticipationDefinition(tombstoneElement, TOMBSTONE_RULE_DEFINITION)

  return Object.freeze({
    id: TOMBSTONE_RULE_DEFINITION.id,
    name: TOMBSTONE_RULE_DEFINITION.name,
    tokens: Object.freeze([
      tombstoneElement.tokens[0]!,
      tombstoneElement.tokens[1]!,
    ]) as typeof TOMBSTONE_RULE_DEFINITION.tokens,
  })
}

export function readCanonTombstoneRule(
  relations: unknown = syncProtocolRelations,
): CanonTombstoneRule {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[PARTICIPATION_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-PARTICIPATION.source_elements がありません')
  }
  return parseCanonTombstoneRule(relation.source_elements)
}

const V12_BOUNDARY_IDS = new Set(['VF1', 'VF2', 'VF3', 'VF4', 'VF5', 'VF6'])

const V12_BOUNDARY_CONDITIONS = new Set([
  'P1・P2・P4',
  '進行中P3',
  '終了後P3',
  'P1・P2・P4のV12不成立',
  '進行中P3のV12不成立',
  'V12の復旧世代結合',
])

const V12_BOUNDARY_OUTCOMES = new Set([
  'V12必須',
  'V12不要',
  'B4',
  'B9',
  '現D4',
  '現復旧世代',
  '保持端末',
])

export type CanonV12BoundaryRule = Readonly<{
  id: string
  condition: string
  outcomes: readonly string[]
  effect: CanonV12BoundaryEffect
}>

type CanonV12BoundaryEffect =
  | Readonly<{ kind: 'presence'; required: boolean }>
  | Readonly<{ kind: 'failure'; result: 'B4' | 'B9' }>
  | Readonly<{
      kind: 'binding'
      components: readonly ['現D4', '現復旧世代', '保持端末']
    }>

function parseV12BoundaryEffect(
  sourceElement: string,
  outcomes: readonly string[],
): CanonV12BoundaryEffect {
  if (hasExactTokens(outcomes, ['V12必須'])) {
    return { kind: 'presence', required: true }
  }
  if (hasExactTokens(outcomes, ['V12不要'])) {
    return { kind: 'presence', required: false }
  }
  if (hasExactTokens(outcomes, ['B4']) || hasExactTokens(outcomes, ['B9'])) {
    return { kind: 'failure', result: outcomes[0] as 'B4' | 'B9' }
  }
  if (hasExactTokens(outcomes, ['現D4', '現復旧世代', '保持端末'])) {
    return {
      kind: 'binding',
      components: ['現D4', '現復旧世代', '保持端末'],
    }
  }
  throw new Error(`R-V12-BOUNDARY の帰結が不正です: ${sourceElement}`)
}

export function parseCanonV12BoundaryRules(
  sourceElements: readonly unknown[],
): readonly CanonV12BoundaryRule[] {
  const seenIds = new Set<string>()

  return sourceElements.map((sourceElement) => {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-V12-BOUNDARY の要素は文字列でなければなりません')
    }

    const separatorIndex = sourceElement.indexOf(':')
    if (
      separatorIndex <= 0 ||
      sourceElement.indexOf(':', separatorIndex + 1) >= 0
    ) {
      throw new Error(`R-V12-BOUNDARY の形式が不正です: ${sourceElement}`)
    }

    const id = sourceElement.slice(0, separatorIndex)
    const body = sourceElement.slice(separatorIndex + 1)
    const equalsIndex = body.indexOf('=')
    if (equalsIndex <= 0 || body.indexOf('=', equalsIndex + 1) >= 0) {
      throw new Error(`R-V12-BOUNDARY の形式が不正です: ${sourceElement}`)
    }

    const condition = body.slice(0, equalsIndex)
    const outcomes = body.slice(equalsIndex + 1).split('+')

    if (!V12_BOUNDARY_IDS.has(id) || seenIds.has(id)) {
      throw new Error(`R-V12-BOUNDARY の ID が不正です: ${id}`)
    }
    if (!V12_BOUNDARY_CONDITIONS.has(condition)) {
      throw new Error(`R-V12-BOUNDARY の条件が不正です: ${condition}`)
    }
    if (
      outcomes.length === 0 ||
      outcomes.some(
        (outcome) =>
          outcome.length === 0 || !V12_BOUNDARY_OUTCOMES.has(outcome),
      )
    ) {
      throw new Error(`R-V12-BOUNDARY の帰結が不正です: ${sourceElement}`)
    }

    const effect = parseV12BoundaryEffect(sourceElement, outcomes)

    seenIds.add(id)
    return Object.freeze({
      id,
      condition,
      outcomes: Object.freeze(outcomes),
      effect: Object.freeze(effect),
    })
  })
}

export function readCanonV12BoundaryRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonV12BoundaryRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[V12_BOUNDARY_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-V12-BOUNDARY.source_elements がありません')
  }
  return parseCanonV12BoundaryRules(relation.source_elements)
}

type IdempotencyRelationId =
  typeof D1_BOUNDARY_RELATION_ID | typeof P3_BOUNDARY_RELATION_ID

type OutOfScopeId = Readonly<{
  id: string
  reason: string
}>

// 射程外行は ID の存在だけを照合し、右辺を読まないため、右辺だけの変更は検出しない。
export const CANON_IDEMPOTENCY_OUT_OF_SCOPE = {
  [D1_BOUNDARY_RELATION_ID]: [
    { id: 'B1', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B2', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B3', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B4', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B5', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B6', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B7', reason: 'D1 付き経路の完全な境界結果集合に属するため' },
    { id: 'B3a', reason: 'T9 の保存を伴い TSK-330 が受け取るため' },
    {
      id: 'DI5',
      reason:
        '混在バッチの A5 を扱い、B3a が T9 の永続化を伴うため TSK-330 の射程とする',
    },
  ],
  [P3_BOUNDARY_RELATION_ID]: [
    { id: '変更受理', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B8', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B9', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B10', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B11', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B12', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B13', reason: 'P3 の完全な境界結果集合に属するため' },
    { id: 'B14', reason: 'P3 の完全な境界結果集合に属するため' },
    {
      id: 'I5',
      reason: '無効化意図の保存・配信を伴い TSK-330 が受け取るため',
    },
    {
      id: 'I6',
      reason: 'P3 受理結果の端末永続化を伴い TSK-330 が受け取るため',
    },
  ],
} as const satisfies Readonly<
  Record<IdempotencyRelationId, readonly OutOfScopeId[]>
>

const CANON_P3_ACCEPTED_RESULT_ID =
  CANON_IDEMPOTENCY_OUT_OF_SCOPE[P3_BOUNDARY_RELATION_ID][0].id

const IMPLEMENTED_IDEMPOTENCY_IDS = {
  [D1_BOUNDARY_RELATION_ID]: new Set<string>(['DI2', 'DI3']),
  [P3_BOUNDARY_RELATION_ID]: new Set<string>(['I2', 'I3']),
} as const

const IMPLEMENTED_PROCESSING_STAGE_IDS = {
  [D1_BOUNDARY_RELATION_ID]: new Set<string>(['DI1', 'DI4', 'RG1']),
  [P3_BOUNDARY_RELATION_ID]: new Set<string>(['I1', 'I4', 'RG1']),
} as const

const IMPLEMENTED_B3_BRANCH_IDS = {
  [D1_BOUNDARY_RELATION_ID]: new Set<string>(['B3b']),
  [P3_BOUNDARY_RELATION_ID]: new Set<string>(),
} as const

const OUT_OF_SCOPE_IDEMPOTENCY_IDS = {
  [D1_BOUNDARY_RELATION_ID]: new Set<string>(
    CANON_IDEMPOTENCY_OUT_OF_SCOPE[D1_BOUNDARY_RELATION_ID].map(
      (element) => element.id,
    ),
  ),
  [P3_BOUNDARY_RELATION_ID]: new Set<string>(
    CANON_IDEMPOTENCY_OUT_OF_SCOPE[P3_BOUNDARY_RELATION_ID].map(
      (element) => element.id,
    ),
  ),
} as const

const EXPECTED_IDEMPOTENCY_IDS = {
  [D1_BOUNDARY_RELATION_ID]: new Set<string>([
    ...IMPLEMENTED_IDEMPOTENCY_IDS[D1_BOUNDARY_RELATION_ID],
    ...IMPLEMENTED_PROCESSING_STAGE_IDS[D1_BOUNDARY_RELATION_ID],
    ...IMPLEMENTED_B3_BRANCH_IDS[D1_BOUNDARY_RELATION_ID],
    ...OUT_OF_SCOPE_IDEMPOTENCY_IDS[D1_BOUNDARY_RELATION_ID],
  ]),
  [P3_BOUNDARY_RELATION_ID]: new Set<string>([
    ...IMPLEMENTED_IDEMPOTENCY_IDS[P3_BOUNDARY_RELATION_ID],
    ...IMPLEMENTED_PROCESSING_STAGE_IDS[P3_BOUNDARY_RELATION_ID],
    ...IMPLEMENTED_B3_BRANCH_IDS[P3_BOUNDARY_RELATION_ID],
    ...OUT_OF_SCOPE_IDEMPOTENCY_IDS[P3_BOUNDARY_RELATION_ID],
  ]),
} as const

const CANON_BOUNDARY_RESULT_ID_PATTERN = /^B[1-7]$/
const CANON_BOUNDARY_RESULT_IDS = new Set<string>(
  [...EXPECTED_IDEMPOTENCY_IDS[D1_BOUNDARY_RELATION_ID]].filter((id) =>
    CANON_BOUNDARY_RESULT_ID_PATTERN.test(id),
  ),
)
const CANON_P3_REJECTION_RESULT_ID_PATTERN = /^B(?:[89]|1[0-4])$/
const CANON_P3_BOUNDARY_RESULT_IDS = new Set<string>(
  [...EXPECTED_IDEMPOTENCY_IDS[P3_BOUNDARY_RELATION_ID]].filter(
    (id) =>
      id === CANON_P3_ACCEPTED_RESULT_ID ||
      CANON_P3_REJECTION_RESULT_ID_PATTERN.test(id),
  ),
)

export type CanonBoundaryResult = Readonly<{
  id: string
  name: string
}>

export type CanonP3BoundaryResult =
  | Readonly<{ id: string; name: string; accepted: true }>
  | Readonly<{ id: string; name: string; accepted: false }>

export type CanonIdempotencyCollisionRule = Readonly<{
  purpose: 'idempotency-collision'
  relationId: IdempotencyRelationId
  id: string
  rightHandSide: string
}>

export type CanonProcessingStageRule = Readonly<{
  purpose: 'processing-stage'
  relationId: IdempotencyRelationId
  id: string
  rightHandSide: string
}>

export type CanonB3BranchRule = Readonly<{
  purpose: 'b3-branch'
  relationId: IdempotencyRelationId
  id: string
  rightHandSide: string
}>

type CanonImplementedRelationRule =
  CanonIdempotencyCollisionRule | CanonProcessingStageRule | CanonB3BranchRule

function assertExactKnownIds(
  relationId: string,
  seenIds: ReadonlySet<string>,
  expectedIds: ReadonlySet<string>,
): void {
  const missingIds = [...expectedIds].filter((id) => !seenIds.has(id))
  const unexpectedIds = [...seenIds].filter((id) => !expectedIds.has(id))
  if (missingIds.length > 0 || unexpectedIds.length > 0) {
    throw new Error(
      `${relationId} の既知 ID 集合が一致しません: 不足=${missingIds.join(',')} 超過=${unexpectedIds.join(',')}`,
    )
  }
}

export function parseCanonBoundaryResults(
  sourceElements: readonly unknown[],
): readonly CanonBoundaryResult[] {
  const seenIds = new Set<string>()
  const results: CanonBoundaryResult[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-BOUNDARY の要素は文字列でなければなりません')
    }

    const separatorIndex = sourceElement.indexOf(':')
    const id =
      separatorIndex < 0
        ? sourceElement
        : sourceElement.slice(0, separatorIndex)
    if (id.length === 0 || seenIds.has(id)) {
      throw new Error(`R-BOUNDARY の ID が不正です: ${id}`)
    }
    seenIds.add(id)

    if (CANON_BOUNDARY_RESULT_IDS.has(id)) {
      if (
        separatorIndex <= 0 ||
        separatorIndex === sourceElement.length - 1 ||
        sourceElement.indexOf(':', separatorIndex + 1) >= 0
      ) {
        throw new Error(`R-BOUNDARY の境界結果形式が不正です: ${sourceElement}`)
      }
      results.push(
        Object.freeze({
          id,
          name: sourceElement.slice(separatorIndex + 1),
        }),
      )
    } else if (!EXPECTED_IDEMPOTENCY_IDS[D1_BOUNDARY_RELATION_ID].has(id)) {
      throw new Error(`R-BOUNDARY に未知の ID があります: ${id}`)
    }
  }

  assertExactKnownIds(
    D1_BOUNDARY_RELATION_ID,
    seenIds,
    EXPECTED_IDEMPOTENCY_IDS[D1_BOUNDARY_RELATION_ID],
  )
  assertExactKnownIds(
    'R-BOUNDARY の境界結果',
    new Set(results.map((result) => result.id)),
    CANON_BOUNDARY_RESULT_IDS,
  )
  return Object.freeze(results)
}

export function readCanonBoundaryResults(
  relations: unknown = syncProtocolRelations,
): readonly CanonBoundaryResult[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[D1_BOUNDARY_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-BOUNDARY.source_elements がありません')
  }
  return parseCanonBoundaryResults(relation.source_elements)
}

export function parseCanonP3BoundaryResults(
  sourceElements: readonly unknown[],
): readonly CanonP3BoundaryResult[] {
  const seenIds = new Set<string>()
  const results: CanonP3BoundaryResult[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-P3-BOUNDARY の要素は文字列でなければなりません')
    }

    const separatorIndex = sourceElement.indexOf(':')
    const id =
      separatorIndex < 0
        ? sourceElement
        : sourceElement.slice(0, separatorIndex)
    if (id.length === 0 || seenIds.has(id)) {
      throw new Error(`R-P3-BOUNDARY の ID が不正です: ${id}`)
    }
    seenIds.add(id)

    if (CANON_P3_BOUNDARY_RESULT_IDS.has(id)) {
      if (id === CANON_P3_ACCEPTED_RESULT_ID) {
        if (separatorIndex >= 0) {
          throw new Error(
            `R-P3-BOUNDARY の受理結果形式が不正です: ${sourceElement}`,
          )
        }
        results.push(Object.freeze({ id, name: sourceElement, accepted: true }))
      } else {
        if (
          separatorIndex <= 0 ||
          separatorIndex === sourceElement.length - 1 ||
          sourceElement.indexOf(':', separatorIndex + 1) >= 0
        ) {
          throw new Error(
            `R-P3-BOUNDARY の拒否結果形式が不正です: ${sourceElement}`,
          )
        }
        results.push(
          Object.freeze({
            id,
            name: sourceElement.slice(separatorIndex + 1),
            accepted: false,
          }),
        )
      }
    } else if (!EXPECTED_IDEMPOTENCY_IDS[P3_BOUNDARY_RELATION_ID].has(id)) {
      throw new Error(`R-P3-BOUNDARY に未知の ID があります: ${id}`)
    }
  }

  assertExactKnownIds(
    P3_BOUNDARY_RELATION_ID,
    seenIds,
    EXPECTED_IDEMPOTENCY_IDS[P3_BOUNDARY_RELATION_ID],
  )
  assertExactKnownIds(
    'R-P3-BOUNDARY の境界結果',
    new Set(results.map((result) => result.id)),
    CANON_P3_BOUNDARY_RESULT_IDS,
  )
  return Object.freeze(results)
}

export function readCanonP3BoundaryResults(
  relations: unknown = syncProtocolRelations,
): readonly CanonP3BoundaryResult[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[P3_BOUNDARY_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-P3-BOUNDARY.source_elements がありません')
  }
  return parseCanonP3BoundaryResults(relation.source_elements)
}

function parseIdempotencyRelation(
  relationId: IdempotencyRelationId,
  sourceElements: readonly unknown[],
): readonly CanonImplementedRelationRule[] {
  const seenIds = new Set<string>()
  const rules: CanonImplementedRelationRule[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error(`${relationId} の要素は文字列でなければなりません`)
    }

    const separatorIndex = sourceElement.indexOf(':')
    const id =
      separatorIndex < 0
        ? sourceElement
        : sourceElement.slice(0, separatorIndex)
    if (id.length === 0 || seenIds.has(id)) {
      throw new Error(`${relationId} の ID が不正です: ${id}`)
    }
    seenIds.add(id)

    const purpose = IMPLEMENTED_IDEMPOTENCY_IDS[relationId].has(id)
      ? 'idempotency-collision'
      : IMPLEMENTED_PROCESSING_STAGE_IDS[relationId].has(id)
        ? 'processing-stage'
        : IMPLEMENTED_B3_BRANCH_IDS[relationId].has(id)
          ? 'b3-branch'
          : undefined
    if (purpose) {
      const equalsIndex = sourceElement.indexOf('=', separatorIndex + 1)
      if (
        separatorIndex <= 0 ||
        equalsIndex <= separatorIndex + 1 ||
        sourceElement.indexOf('=', equalsIndex + 1) >= 0 ||
        equalsIndex === sourceElement.length - 1
      ) {
        throw new Error(`${relationId} の要素形式が不正です: ${sourceElement}`)
      }
      rules.push(
        Object.freeze({
          purpose,
          relationId,
          id,
          rightHandSide: sourceElement.slice(equalsIndex + 1),
        }),
      )
    } else if (!OUT_OF_SCOPE_IDEMPOTENCY_IDS[relationId].has(id)) {
      throw new Error(`${relationId} に未知の ID があります: ${id}`)
    }
  }

  assertExactKnownIds(relationId, seenIds, EXPECTED_IDEMPOTENCY_IDS[relationId])
  return Object.freeze(rules)
}

export function parseCanonIdempotencyCollisionRules(
  d1SourceElements: readonly unknown[],
  p3SourceElements: readonly unknown[],
): readonly CanonIdempotencyCollisionRule[] {
  const rules = [
    ...parseIdempotencyRelation(D1_BOUNDARY_RELATION_ID, d1SourceElements),
    ...parseIdempotencyRelation(P3_BOUNDARY_RELATION_ID, p3SourceElements),
  ].filter((rule): rule is CanonIdempotencyCollisionRule =>
    Object.is(rule.purpose, 'idempotency-collision'),
  )
  return Object.freeze(rules)
}

export function readCanonIdempotencyCollisionRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonIdempotencyCollisionRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const d1Relation = relations[D1_BOUNDARY_RELATION_ID]
  const p3Relation = relations[P3_BOUNDARY_RELATION_ID]
  if (
    !isRecord(d1Relation) ||
    !Array.isArray(d1Relation.source_elements) ||
    !isRecord(p3Relation) ||
    !Array.isArray(p3Relation.source_elements)
  ) {
    throw new Error('D5 衝突規則の source_elements がありません')
  }
  return parseCanonIdempotencyCollisionRules(
    d1Relation.source_elements,
    p3Relation.source_elements,
  )
}

export function readCanonProcessingStageRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonProcessingStageRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const d1Relation = relations[D1_BOUNDARY_RELATION_ID]
  const p3Relation = relations[P3_BOUNDARY_RELATION_ID]
  if (
    !isRecord(d1Relation) ||
    !Array.isArray(d1Relation.source_elements) ||
    !isRecord(p3Relation) ||
    !Array.isArray(p3Relation.source_elements)
  ) {
    throw new Error('処理段階規則の source_elements がありません')
  }
  const rules = [
    ...parseIdempotencyRelation(
      D1_BOUNDARY_RELATION_ID,
      d1Relation.source_elements,
    ),
    ...parseIdempotencyRelation(
      P3_BOUNDARY_RELATION_ID,
      p3Relation.source_elements,
    ),
  ].filter((rule): rule is CanonProcessingStageRule =>
    Object.is(rule.purpose, 'processing-stage'),
  )
  return Object.freeze(rules)
}

export function readCanonB3BranchRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonB3BranchRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const d1Relation = relations[D1_BOUNDARY_RELATION_ID]
  const p3Relation = relations[P3_BOUNDARY_RELATION_ID]
  if (
    !isRecord(d1Relation) ||
    !Array.isArray(d1Relation.source_elements) ||
    !isRecord(p3Relation) ||
    !Array.isArray(p3Relation.source_elements)
  ) {
    throw new Error('B3 分岐規則の source_elements がありません')
  }
  const rules = [
    ...parseIdempotencyRelation(
      D1_BOUNDARY_RELATION_ID,
      d1Relation.source_elements,
    ),
    ...parseIdempotencyRelation(
      P3_BOUNDARY_RELATION_ID,
      p3Relation.source_elements,
    ),
  ].filter((rule): rule is CanonB3BranchRule =>
    Object.is(rule.purpose, 'b3-branch'),
  )
  return Object.freeze(rules)
}

// 射程外行は ID の存在だけを照合し、右辺を読まないため、右辺だけの変更は検出しない。
export const CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE = [
  { id: 'C1', reason: '応答で写像を返す7章の契約に依存するため' },
] as const

const IMPLEMENTED_TEMPORARY_ID_MAPPING_IDS = new Set<string>(['C2', 'C3', 'C4'])
const OUT_OF_SCOPE_TEMPORARY_ID_MAPPING_IDS = new Set<string>(
  CANON_TEMPORARY_ID_MAPPING_OUT_OF_SCOPE.map((element) => element.id),
)
const EXPECTED_TEMPORARY_ID_MAPPING_IDS = new Set<string>([
  ...IMPLEMENTED_TEMPORARY_ID_MAPPING_IDS,
  ...OUT_OF_SCOPE_TEMPORARY_ID_MAPPING_IDS,
])

export type CanonTemporaryIdMappingRule = Readonly<{
  id: string
  rightHandSide: string
}>

export function parseCanonTemporaryIdMappingRules(
  sourceElements: readonly unknown[],
): readonly CanonTemporaryIdMappingRule[] {
  const seenIds = new Set<string>()
  const rules: CanonTemporaryIdMappingRule[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-TEMP-ID-MAPPING の要素は文字列でなければなりません')
    }

    const separatorIndex = sourceElement.indexOf(':')
    if (
      separatorIndex <= 0 ||
      separatorIndex === sourceElement.length - 1 ||
      sourceElement.indexOf(':', separatorIndex + 1) >= 0
    ) {
      throw new Error(`R-TEMP-ID-MAPPING の形式が不正です: ${sourceElement}`)
    }

    const id = sourceElement.slice(0, separatorIndex)
    if (seenIds.has(id)) {
      throw new Error(`R-TEMP-ID-MAPPING の ID が重複しています: ${id}`)
    }
    seenIds.add(id)

    if (IMPLEMENTED_TEMPORARY_ID_MAPPING_IDS.has(id)) {
      rules.push(
        Object.freeze({
          id,
          rightHandSide: sourceElement.slice(separatorIndex + 1),
        }),
      )
    } else if (!OUT_OF_SCOPE_TEMPORARY_ID_MAPPING_IDS.has(id)) {
      throw new Error(`R-TEMP-ID-MAPPING に未知の ID があります: ${id}`)
    }
  }

  assertExactKnownIds(
    TEMPORARY_ID_MAPPING_RELATION_ID,
    seenIds,
    EXPECTED_TEMPORARY_ID_MAPPING_IDS,
  )
  return Object.freeze(rules)
}

export function readCanonTemporaryIdMappingRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonTemporaryIdMappingRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[TEMPORARY_ID_MAPPING_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-TEMP-ID-MAPPING.source_elements がありません')
  }
  return parseCanonTemporaryIdMappingRules(relation.source_elements)
}

const CANON_TXN_ROUTE_IDS = ['P1', 'P2', 'P3', 'P4', 'P5'] as const
const CANON_TXN_STEP_IDS = [
  'T1',
  'T2',
  'T3',
  'T4',
  'T5',
  'T6',
  'T7',
  'T8',
  'T9',
] as const
const CANON_TXN_ROUTE_ID_PATTERN = /^P[1-5]$/
const CANON_TXN_STEP_ID_PATTERN = /^T[1-9]$/
const CANON_TXN_EXPECTED_IDS = new Set<string>([
  ...CANON_TXN_ROUTE_IDS,
  ...CANON_TXN_STEP_IDS,
])
const CANON_TXN_EXPECTED_STEP_IDS = new Set<string>(CANON_TXN_STEP_IDS)

type CanonTxnRouteId = (typeof CANON_TXN_ROUTE_IDS)[number]
type CanonTxnStepId = (typeof CANON_TXN_STEP_IDS)[number]

export type CanonTxnRouteRule =
  | Readonly<{
      kind: 'route'
      id: CanonTxnRouteId
      name: string
      stepIds: readonly CanonTxnStepId[]
    }>
  | Readonly<{
      kind: 'step'
      id: CanonTxnStepId
      name: string
    }>

export function parseCanonTxnRouteRules(
  sourceElements: readonly unknown[],
): readonly CanonTxnRouteRule[] {
  const seenIds = new Set<string>()
  const referencedStepIds = new Set<string>()
  const rules: CanonTxnRouteRule[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-TXN-ROUTE の要素は文字列でなければなりません')
    }

    const separatorIndex = sourceElement.indexOf(':')
    const id =
      separatorIndex < 0
        ? sourceElement
        : sourceElement.slice(0, separatorIndex)
    const isRoute = CANON_TXN_ROUTE_ID_PATTERN.test(id)
    const isStep = CANON_TXN_STEP_ID_PATTERN.test(id)
    if (!isRoute && !isStep) {
      throw new Error(`R-TXN-ROUTE に未知の ID があります: ${id}`)
    }
    if (seenIds.has(id)) {
      throw new Error(`R-TXN-ROUTE の ID が重複しています: ${id}`)
    }
    seenIds.add(id)

    if (
      separatorIndex <= 0 ||
      separatorIndex === sourceElement.length - 1 ||
      sourceElement.indexOf(':', separatorIndex + 1) >= 0
    ) {
      throw new Error(`R-TXN-ROUTE の要素形式が不正です: ${sourceElement}`)
    }

    const body = sourceElement.slice(separatorIndex + 1)
    if (isRoute) {
      const equalsIndex = body.indexOf('=')
      if (
        equalsIndex <= 0 ||
        equalsIndex === body.length - 1 ||
        body.indexOf('=', equalsIndex + 1) >= 0
      ) {
        throw new Error(`R-TXN-ROUTE の経路形式が不正です: ${sourceElement}`)
      }

      const name = body.slice(0, equalsIndex)
      const stepIds = body.slice(equalsIndex + 1).split(',')
      const uniqueStepIds = new Set(stepIds)
      if (
        stepIds.some((stepId) => !CANON_TXN_STEP_ID_PATTERN.test(stepId)) ||
        uniqueStepIds.size !== stepIds.length
      ) {
        throw new Error(`R-TXN-ROUTE の参照 T 要素が不正です: ${sourceElement}`)
      }

      for (const stepId of stepIds) {
        referencedStepIds.add(stepId)
      }
      rules.push(
        Object.freeze({
          kind: 'route',
          id: id as CanonTxnRouteId,
          name,
          stepIds: Object.freeze(stepIds as CanonTxnStepId[]),
        }),
      )
      continue
    }

    if (body.includes('=')) {
      throw new Error(`R-TXN-ROUTE の T 要素形式が不正です: ${sourceElement}`)
    }
    rules.push(
      Object.freeze({
        kind: 'step',
        id: id as CanonTxnStepId,
        name: body,
      }),
    )
  }

  assertExactKnownIds(TXN_ROUTE_RELATION_ID, seenIds, CANON_TXN_EXPECTED_IDS)
  assertExactKnownIds(
    'R-TXN-ROUTE の参照 T 要素',
    referencedStepIds,
    CANON_TXN_EXPECTED_STEP_IDS,
  )
  return Object.freeze(rules)
}

export function readCanonTxnRouteRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonTxnRouteRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[TXN_ROUTE_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-TXN-ROUTE.source_elements がありません')
  }
  return parseCanonTxnRouteRules(relation.source_elements)
}

const CANON_QUEUE_STATE_IDS = [
  '未送信',
  '要操作',
  '同期済み',
  '退避済み',
] as const
type CanonQueueStateId = (typeof CANON_QUEUE_STATE_IDS)[number]
const CANON_QUEUE_STATE_ID_SET = new Set<string>(CANON_QUEUE_STATE_IDS)

const CANON_I6_ID = 'I6'
const CANON_I6_NAME = 'P3受理結果の端末保持'
const CANON_I6_HOLDING_ELEMENT_IDS = [
  '端末永続化まで成立した対象参照',
  'V11の版',
  'D5',
  '確定内容',
  'accepted_atを起点',
  '同期済みと同じ24時間保持',
  '保存済み結果の再掲で延長しない',
  'サーバー確定から端末永続化まで保護なし',
  'RG1中は自動破棄停止',
  '退避・閲覧・書き出し対象',
  '復元規則なし',
] as const
type CanonI6HoldingElementId = (typeof CANON_I6_HOLDING_ELEMENT_IDS)[number]
const CANON_I6_HOLDING_ELEMENT_ID_SET = new Set<string>(
  CANON_I6_HOLDING_ELEMENT_IDS,
)

export type CanonQueueLifeRule =
  | Readonly<{
      kind: 'state'
      id: CanonQueueStateId
    }>
  | Readonly<{
      kind: 'holding-contract'
      id: typeof CANON_I6_ID
      name: typeof CANON_I6_NAME
      elements: readonly Readonly<{ id: CanonI6HoldingElementId }>[]
    }>

function isCanonQueueStateId(value: string): value is CanonQueueStateId {
  return CANON_QUEUE_STATE_ID_SET.has(value)
}

function isCanonI6HoldingElementId(
  value: string,
): value is CanonI6HoldingElementId {
  return CANON_I6_HOLDING_ELEMENT_ID_SET.has(value)
}

function parseCanonI6HoldingRule(sourceElement: string): CanonQueueLifeRule {
  const separatorIndex = sourceElement.indexOf(':')
  const equalsIndex = sourceElement.indexOf('=', separatorIndex + 1)
  if (
    separatorIndex <= 0 ||
    equalsIndex <= separatorIndex + 1 ||
    sourceElement.indexOf(':', separatorIndex + 1) >= 0 ||
    sourceElement.indexOf('=', equalsIndex + 1) >= 0
  ) {
    throw new Error(`R-QUEUE-LIFE の I6 形式が不正です: ${sourceElement}`)
  }

  const id = sourceElement.slice(0, separatorIndex)
  const name = sourceElement.slice(separatorIndex + 1, equalsIndex)
  if (id !== CANON_I6_ID || name !== CANON_I6_NAME) {
    throw new Error(`R-QUEUE-LIFE の I6 定義が不正です: ${sourceElement}`)
  }

  const tokens = sourceElement.slice(equalsIndex + 1).split('+')
  const tokenIds = new Set<string>()
  const elements: Readonly<{ id: CanonI6HoldingElementId }>[] = []
  for (const token of tokens) {
    if (!isCanonI6HoldingElementId(token)) {
      throw new Error(`R-QUEUE-LIFE の未知の I6 トークンです: ${token}`)
    }
    tokenIds.add(token)
    elements.push(Object.freeze({ id: token }))
  }
  if (
    tokens.length !== CANON_I6_HOLDING_ELEMENT_IDS.length ||
    tokenIds.size !== tokens.length
  ) {
    throw new Error('R-QUEUE-LIFE の I6 トークン集合が一致しません')
  }
  assertExactKnownIds(
    `${QUEUE_LIFE_RELATION_ID}.${CANON_I6_ID}`,
    tokenIds,
    CANON_I6_HOLDING_ELEMENT_ID_SET,
  )

  return Object.freeze({
    kind: 'holding-contract',
    id: CANON_I6_ID,
    name: CANON_I6_NAME,
    elements: Object.freeze(elements),
  })
}

export function parseCanonQueueLifeRules(
  sourceElements: readonly unknown[],
): readonly CanonQueueLifeRule[] {
  const seenIds = new Set<string>()
  const rules: CanonQueueLifeRule[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-QUEUE-LIFE の要素は文字列でなければなりません')
    }

    let rule: CanonQueueLifeRule
    if (isCanonQueueStateId(sourceElement)) {
      rule = Object.freeze({ kind: 'state', id: sourceElement })
    } else if (sourceElement.startsWith(`${CANON_I6_ID}:`)) {
      rule = parseCanonI6HoldingRule(sourceElement)
    } else {
      throw new Error(
        `R-QUEUE-LIFE に未知の状態または ID があります: ${sourceElement}`,
      )
    }

    if (seenIds.has(rule.id)) {
      throw new Error(`R-QUEUE-LIFE の ID が重複しています: ${rule.id}`)
    }
    seenIds.add(rule.id)
    rules.push(rule)
  }

  assertExactKnownIds(
    QUEUE_LIFE_RELATION_ID,
    seenIds,
    new Set<string>([...CANON_QUEUE_STATE_IDS, CANON_I6_ID]),
  )
  return Object.freeze(rules)
}

export function readCanonQueueLifeRules(
  relations: unknown = syncProtocolRelations,
): readonly CanonQueueLifeRule[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[QUEUE_LIFE_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-QUEUE-LIFE.source_elements がありません')
  }
  return parseCanonQueueLifeRules(relation.source_elements)
}

export const CANON_ACK_STATE_RESULT = {
  ACCEPTED: '受理',
  DUPLICATE: '重複',
  REJECTED: '拒否',
  EVACUATED: '退避',
  UNPROCESSED: '未処理',
} as const

const CANON_ACK_STATE_RESULT_IDS = Object.freeze(
  Object.values(CANON_ACK_STATE_RESULT),
)
const CANON_ACK_STATE_RESULT_ID_SET = new Set<string>(
  CANON_ACK_STATE_RESULT_IDS,
)

export type CanonAckStateResult = Readonly<{ id: string }>

export function parseCanonAckStateResults(
  sourceElements: readonly unknown[],
): readonly CanonAckStateResult[] {
  const seenIds = new Set<string>()
  const results: CanonAckStateResult[] = []

  for (const sourceElement of sourceElements) {
    if (typeof sourceElement !== 'string') {
      throw new Error('R-ACK-STATE の要素は文字列でなければなりません')
    }
    if (!CANON_ACK_STATE_RESULT_ID_SET.has(sourceElement)) {
      throw new Error(`R-ACK-STATE に未知の要素があります: ${sourceElement}`)
    }
    if (seenIds.has(sourceElement)) {
      throw new Error(`R-ACK-STATE の要素が重複しています: ${sourceElement}`)
    }
    seenIds.add(sourceElement)
    results.push(Object.freeze({ id: sourceElement }))
  }

  assertExactKnownIds(
    ACK_STATE_RELATION_ID,
    seenIds,
    CANON_ACK_STATE_RESULT_ID_SET,
  )
  return Object.freeze(results)
}

export function readCanonAckStateResults(
  relations: unknown = syncProtocolRelations,
): readonly CanonAckStateResult[] {
  if (!isRecord(relations)) {
    throw new Error('設計関係 JSON の形式が不正です')
  }
  const relation = relations[ACK_STATE_RELATION_ID]
  if (!isRecord(relation) || !Array.isArray(relation.source_elements)) {
    throw new Error('R-ACK-STATE.source_elements がありません')
  }
  return parseCanonAckStateResults(relation.source_elements)
}

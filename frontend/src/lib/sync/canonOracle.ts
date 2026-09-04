// このパーサは docs/design/sync-protocol.md 4-3（V1〜V12 と V12 条件・結果写像）と 5-5 の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
// テストからのみ使う。
import syncProtocolRelations from '@design-relations/sync-protocol.json'
import { EVENT_KIND_RULES } from './eventKinds'

const EVENT_FIELD_RELATION_ID = 'R-EVENT-FIELD'
const EVENT_FIELD_ID_PATTERN = /^V\d+$/
const PARTICIPATION_RELATION_ID = 'R-PARTICIPATION'
const V12_BOUNDARY_RELATION_ID = 'R-V12-BOUNDARY'
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
// K5 はキュー遷移に属する墓標生成条件のため、既知の射程外定義として検証後に取り込まない。
const OUT_OF_SCOPE_PARTICIPATION_DEFINITION = {
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
  let hasOutOfScopeDefinition = false
  const eventKinds: CanonEventKindRule[] = []
  for (const element of elements) {
    if (element.id === REVISION_ORDER_DEFINITION.id) {
      assertParticipationDefinition(element, REVISION_ORDER_DEFINITION)
      hasRevisionOrderDefinition = true
    } else if (element.id === OUT_OF_SCOPE_PARTICIPATION_DEFINITION.id) {
      assertParticipationDefinition(
        element,
        OUT_OF_SCOPE_PARTICIPATION_DEFINITION,
      )
      hasOutOfScopeDefinition = true
    } else {
      eventKinds.push(parseEventKindParticipation(element))
    }
  }
  if (!hasRevisionOrderDefinition || !hasOutOfScopeDefinition) {
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

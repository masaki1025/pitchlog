// この表と条件写像は docs/design/sync-protocol.md 4-3（V1〜V12）と 4-3-A の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
import {
  EVENT_PARTICIPATION,
  type EventKind,
  type EventParticipation,
} from './eventKinds'

export const EVENT_FIELD_REQUIREDNESS = {
  UNCONDITIONAL: '全イベントで無条件',
  EVENT_KIND_CONDITIONAL: '種別条件付き',
  REQUEST_LEVEL: '要求レベル',
} as const

export type EventFieldRequiredness =
  (typeof EVENT_FIELD_REQUIREDNESS)[keyof typeof EVENT_FIELD_REQUIREDNESS]

const OPAQUE_FIELD_SHAPE = { kind: 'opaque' } as const
const TARGET_REFERENCE_FIELD_SHAPE = {
  kind: 'composite',
  elements: ['試合', '対象の D4', '対象の D1'],
} as const

export type EventFieldShape =
  typeof OPAQUE_FIELD_SHAPE | typeof TARGET_REFERENCE_FIELD_SHAPE

type EventFieldRuleDefinition = {
  id: string
  requiredness: EventFieldRequiredness
  conditions: readonly string[]
  shape: EventFieldShape
}

export const EVENT_FIELD_RULES = [
  {
    id: 'V1',
    requiredness: EVENT_FIELD_REQUIREDNESS.UNCONDITIONAL,
    conditions: ['全イベントで無条件'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V2',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['P1・P2・P4に必須', 'P3は持たない'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V3',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['P1・P2・P4に必須', 'P3は持たず'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V4',
    requiredness: EVENT_FIELD_REQUIREDNESS.UNCONDITIONAL,
    conditions: ['全イベントで無条件'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V5',
    requiredness: EVENT_FIELD_REQUIREDNESS.UNCONDITIONAL,
    conditions: ['全イベントで無条件'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V6',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['種別条件付き', 'P3自身は持たず'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V7',
    requiredness: EVENT_FIELD_REQUIREDNESS.UNCONDITIONAL,
    conditions: ['全イベントで無条件'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V8',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['取消可能な操作に限る', 'P3は持たない'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V9',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['墓標・改訂に限る', 'P3は持たない'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V10',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['種別条件付き', 'P3は必須'],
    shape: TARGET_REFERENCE_FIELD_SHAPE,
  },
  {
    id: 'V11',
    requiredness: EVENT_FIELD_REQUIREDNESS.EVENT_KIND_CONDITIONAL,
    conditions: ['P3に必須'],
    shape: OPAQUE_FIELD_SHAPE,
  },
  {
    id: 'V12',
    requiredness: EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL,
    conditions: [
      '要求レベル',
      'P1・P2・P4',
      '進行中のP3',
      '終了後のP3には不要',
    ],
    shape: OPAQUE_FIELD_SHAPE,
  },
] as const satisfies readonly EventFieldRuleDefinition[]

export type EventFieldRule = (typeof EVENT_FIELD_RULES)[number]
type RequestOnlyRule = Extract<
  EventFieldRule,
  { requiredness: typeof EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL }
>
type EventSlotRule = Exclude<EventFieldRule, RequestOnlyRule>

export type RequestOnlyId = RequestOnlyRule['id']
export type EventSlotId = EventSlotRule['id']

function isRequestOnlyRule(rule: EventFieldRule): rule is RequestOnlyRule {
  return rule.requiredness === EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL
}

function isEventSlotRule(rule: EventFieldRule): rule is EventSlotRule {
  return rule.requiredness !== EVENT_FIELD_REQUIREDNESS.REQUEST_LEVEL
}

export const REQUEST_ONLY_IDS: readonly RequestOnlyId[] = Object.freeze(
  EVENT_FIELD_RULES.filter(isRequestOnlyRule).map((rule) => rule.id),
)

export const EVENT_SLOT_IDS: readonly EventSlotId[] = Object.freeze(
  EVENT_FIELD_RULES.filter(isEventSlotRule).map((rule) => rule.id),
)

export const EVENT_IDENTIFIER_SLOT_IDS = [
  'V1',
  'V2',
  'V3',
] as const satisfies readonly EventSlotId[]

export const SYNC_EVENT_PATH = {
  P1: 'P1',
  P2: 'P2',
  P3: 'P3',
  P4: 'P4',
} as const

export type SyncEventPath =
  (typeof SYNC_EVENT_PATH)[keyof typeof SYNC_EVENT_PATH]

export const SYNC_EVENT_PATHS: readonly SyncEventPath[] = Object.freeze(
  Object.values(SYNC_EVENT_PATH),
)

export const EVENT_FIELD_PRESENCE = {
  REQUIRED: 'required',
  FORBIDDEN: 'forbidden',
  OPTIONAL: 'optional',
} as const

export type EventFieldPresence =
  (typeof EVENT_FIELD_PRESENCE)[keyof typeof EVENT_FIELD_PRESENCE]

export type EventFieldConditionContext = {
  path: SyncEventPath
  eventKind: EventKind
  participation: EventParticipation
  cancellable: boolean
}

type ConditionRule = {
  readonly conditions: readonly string[]
  readonly shape: EventFieldShape
}
type ConditionEffect = Exclude<
  EventFieldPresence,
  typeof EVENT_FIELD_PRESENCE.OPTIONAL
>
type ConditionHandler = (
  rule: ConditionRule,
  context: EventFieldConditionContext,
) => ConditionEffect | undefined

const D1_EVENT_PATHS = new Set<SyncEventPath>([
  SYNC_EVENT_PATH.P1,
  SYNC_EVENT_PATH.P2,
  SYNC_EVENT_PATH.P4,
])
const CANCELLABLE_EVENT_KIND_NAMES = new Set(['毎球入力', '状態補正'])
const TOMBSTONE_EVENT_KIND_NAME = '墓標'

const required: ConditionHandler = () => EVENT_FIELD_PRESENCE.REQUIRED
const forbiddenOnP3: ConditionHandler = (_rule, context) =>
  context.path === SYNC_EVENT_PATH.P3
    ? EVENT_FIELD_PRESENCE.FORBIDDEN
    : undefined
const requiredOnD1Path: ConditionHandler = (_rule, context) =>
  D1_EVENT_PATHS.has(context.path) ? EVENT_FIELD_PRESENCE.REQUIRED : undefined
const requiredOnP3: ConditionHandler = (_rule, context) =>
  context.path === SYNC_EVENT_PATH.P3
    ? EVENT_FIELD_PRESENCE.REQUIRED
    : undefined
const requiredOnlyOnP3: ConditionHandler = (_rule, context) =>
  context.path === SYNC_EVENT_PATH.P3
    ? EVENT_FIELD_PRESENCE.REQUIRED
    : EVENT_FIELD_PRESENCE.FORBIDDEN
const forbiddenAsRequestValue: ConditionHandler = () =>
  EVENT_FIELD_PRESENCE.FORBIDDEN

function isReplacementOrTombstone(
  context: EventFieldConditionContext,
): boolean {
  return (
    context.eventKind.name === TOMBSTONE_EVENT_KIND_NAME ||
    context.eventKind.participation === EVENT_PARTICIPATION.INHERIT_SOURCE
  )
}

function requiresTargetReference(context: EventFieldConditionContext): boolean {
  return (
    context.path === SYNC_EVENT_PATH.P3 ||
    context.participation === EVENT_PARTICIPATION.DEPENDENT ||
    isReplacementOrTombstone(context)
  )
}

const requiredByEventKind: ConditionHandler = (rule, context) => {
  const applies =
    rule.shape.kind === 'composite'
      ? requiresTargetReference(context)
      : context.participation === EVENT_PARTICIPATION.LOGICAL_POSITION
  return applies
    ? EVENT_FIELD_PRESENCE.REQUIRED
    : EVENT_FIELD_PRESENCE.FORBIDDEN
}

const requiredWhenCancellable: ConditionHandler = (_rule, context) =>
  context.cancellable
    ? EVENT_FIELD_PRESENCE.REQUIRED
    : EVENT_FIELD_PRESENCE.FORBIDDEN

const requiredForReplacementOrTombstone: ConditionHandler = (_rule, context) =>
  isReplacementOrTombstone(context)
    ? EVENT_FIELD_PRESENCE.REQUIRED
    : EVENT_FIELD_PRESENCE.FORBIDDEN

const CONDITION_HANDLERS = new Map<string, ConditionHandler>([
  ['全イベントで無条件', required],
  ['P1・P2・P4に必須', requiredOnD1Path],
  ['P3は持たない', forbiddenOnP3],
  ['P3は持たず', forbiddenOnP3],
  ['種別条件付き', requiredByEventKind],
  ['P3自身は持たず', forbiddenOnP3],
  ['取消可能な操作に限る', requiredWhenCancellable],
  ['墓標・改訂に限る', requiredForReplacementOrTombstone],
  ['P3は必須', requiredOnP3],
  ['P3に必須', requiredOnlyOnP3],
  ['要求レベル', forbiddenAsRequestValue],
  ['P1・P2・P4', forbiddenAsRequestValue],
  ['進行中のP3', forbiddenAsRequestValue],
  ['終了後のP3には不要', forbiddenAsRequestValue],
])

export function isCancellableEventKind(eventKind: EventKind): boolean {
  return CANCELLABLE_EVENT_KIND_NAMES.has(eventKind.name)
}

export function resolveEventFieldPresence(
  rule: ConditionRule,
  context: EventFieldConditionContext,
): EventFieldPresence {
  const effects = new Set<ConditionEffect>()
  for (const condition of rule.conditions) {
    const handler = CONDITION_HANDLERS.get(condition)
    if (!handler) {
      throw new Error(`未知のイベントフィールド条件です: ${condition}`)
    }
    const effect = handler(rule, context)
    if (effect) {
      effects.add(effect)
    }
  }
  if (effects.size > 1) {
    throw new Error('イベントフィールド条件の評価結果が競合しています')
  }
  return [...effects][0] ?? EVENT_FIELD_PRESENCE.OPTIONAL
}

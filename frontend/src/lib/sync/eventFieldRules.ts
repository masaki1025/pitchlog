// この表は docs/design/sync-protocol.md 4-3（V1〜V12）の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
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

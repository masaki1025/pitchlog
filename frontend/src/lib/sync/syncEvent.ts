// この型と合成関数は docs/design/sync-protocol.md 4-3 と 4-3-A の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
import {
  EVENT_FIELD_RULES,
  type EventFieldRule,
  type EventSlotId,
} from './eventFieldRules'

export const SYNC_EVENT_ENVELOPE_KEYS = Object.freeze(['fields'] as const)

export type SyncEventEnvelopeKey = (typeof SYNC_EVENT_ENVELOPE_KEYS)[number]

export type SyncEvent = {
  [Key in SyncEventEnvelopeKey]: Partial<Record<EventSlotId, unknown>>
}

type CompositeFieldRule = Extract<
  EventFieldRule,
  { shape: { kind: 'composite' } }
>
type TargetEventReferenceElement =
  CompositeFieldRule['shape']['elements'][number]

export type TargetEventReference = {
  [Element in TargetEventReferenceElement]: unknown
}

export type SidecarJoinKey = readonly [unknown, unknown, unknown]

const targetReferenceRule = EVENT_FIELD_RULES.find(
  (rule): rule is CompositeFieldRule => rule.shape.kind === 'composite',
)
if (!targetReferenceRule) {
  throw new Error('対象イベント参照の shape がありません')
}

export const TARGET_EVENT_REFERENCE_ELEMENTS = Object.freeze(
  targetReferenceRule.shape.elements,
)

export function isTargetEventReference(
  value: unknown,
): value is TargetEventReference {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }

  const ownKeys = Reflect.ownKeys(value)
  return (
    ownKeys.length === TARGET_EVENT_REFERENCE_ELEMENTS.length &&
    ownKeys.every(
      (key) =>
        typeof key === 'string' &&
        TARGET_EVENT_REFERENCE_ELEMENTS.includes(
          key as TargetEventReferenceElement,
        ),
    )
  )
}

export function buildSidecarJoinKey(
  game: unknown,
  recordingRightsGeneration: unknown,
  eventSequence: unknown,
): SidecarJoinKey {
  return [game, recordingRightsGeneration, eventSequence]
}

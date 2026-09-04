// この型と合成関数は docs/design/sync-protocol.md 4-3 と 4-3-A の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
import {
  EVENT_FIELD_RULES,
  type EventFieldRule,
  type EventSlotId,
} from './eventFieldRules'
import type { EventKindId } from './eventKinds'

export type SyncEvent = {
  kind: EventKindId
  fields: Partial<Record<EventSlotId, unknown>>
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

export const TARGET_EVENT_REFERENCE_ELEMENTS =
  targetReferenceRule.shape.elements

export function isTargetEventReference(
  value: unknown,
): value is TargetEventReference {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    TARGET_EVENT_REFERENCE_ELEMENTS.every((element) =>
      Object.prototype.hasOwnProperty.call(value, element),
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

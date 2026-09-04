// この検査器は docs/design/sync-protocol.md 4-3 と 4-3-A の写しである。
// 値は実装で決めず、変更は正本の改訂ゲートを通すこと。
import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_RULES,
  EVENT_IDENTIFIER_SLOT_IDS,
  EVENT_SLOT_IDS,
  isCancellableEventKind,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
  SYNC_EVENT_PATHS,
  type EventSlotId,
  type SyncEventPath,
} from './eventFieldRules'
import {
  EVENT_KIND_GROUP,
  EVENT_KIND_RULES,
  EVENT_PARTICIPATION,
  type EventKind,
  type EventKindId,
  type EventParticipation,
} from './eventKinds'
import { isTargetEventReference, type SyncEvent } from './syncEvent'

export const SYNC_EVENT_VIOLATION = {
  INVALID_FIELDS: 'invalid-fields',
  UNKNOWN_KIND: 'unknown-kind',
  ROUTE_KIND_MISMATCH: 'route-kind-mismatch',
  SOURCE_CONTEXT_UNAVAILABLE: 'source-context-unavailable',
  UNKNOWN_SLOT: 'unknown-slot',
  MISSING_SLOT: 'missing-slot',
  FORBIDDEN_SLOT: 'forbidden-slot',
  INVALID_COMPOSITE: 'invalid-composite',
  IDENTIFIER_COLLISION: 'identifier-collision',
  INVALID_FIELD_CONDITION: 'invalid-field-condition',
} as const

export type SyncEventViolationType =
  (typeof SYNC_EVENT_VIOLATION)[keyof typeof SYNC_EVENT_VIOLATION]

export type SyncEventViolation = {
  violation: SyncEventViolationType
  target: string
}

export type SourceEventContext = {
  participation: Exclude<
    EventParticipation,
    typeof EVENT_PARTICIPATION.INHERIT_SOURCE
  >
  cancellable: boolean
}

export type SourceEventContextResolver = (
  event: SyncEvent,
) => SourceEventContext

export type SyncEventValidationContext = {
  path: SyncEventPath
  sourceEventContextResolver?: SourceEventContextResolver
}

export type SyncEventValidationResult =
  { ok: true } | { ok: false; reason: SyncEventViolation }
type SyncEventValidationFailure = Extract<
  SyncEventValidationResult,
  { ok: false }
>

export class SyncEventValidationError extends Error {
  readonly reason: SyncEventViolation

  constructor(reason: SyncEventViolation) {
    super(`${reason.violation}:${reason.target}`)
    this.name = 'SyncEventValidationError'
    this.reason = reason
  }
}

const EVENT_SLOT_ID_SET = new Set<string>(EVENT_SLOT_IDS)
const SYNC_EVENT_PATH_SET = new Set<SyncEventPath>(SYNC_EVENT_PATHS)
const SOURCE_PARTICIPATIONS = new Set<EventParticipation>([
  EVENT_PARTICIPATION.LOGICAL_POSITION,
  EVENT_PARTICIPATION.SYNC_ORDER_ONLY,
  EVENT_PARTICIPATION.DEPENDENT,
])

function failure(
  violation: SyncEventViolationType,
  targetValue: unknown,
): SyncEventValidationFailure {
  const target = String(targetValue)
  return {
    ok: false,
    reason: { violation, target: target.length > 0 ? target : '<empty>' },
  }
}

function isFieldRecord(value: unknown): value is Record<PropertyKey, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isSourceEventContext(value: unknown): value is SourceEventContext {
  if (!isFieldRecord(value)) {
    return false
  }
  return (
    SOURCE_PARTICIPATIONS.has(value.participation as EventParticipation) &&
    typeof value.cancellable === 'boolean'
  )
}

function findEventKind(kind: EventKindId): EventKind | undefined {
  return EVENT_KIND_RULES.find((candidate) => candidate.id === kind)
}

function routeMatchesGroup(eventKind: EventKind, path: SyncEventPath): boolean {
  const isP3 = path === SYNC_EVENT_PATH.P3
  return eventKind.group === EVENT_KIND_GROUP.B ? isP3 : !isP3
}

function resolveKindContext(
  event: SyncEvent,
  eventKind: EventKind,
  context: SyncEventValidationContext,
): SourceEventContext | SyncEventValidationFailure {
  if (eventKind.participation !== EVENT_PARTICIPATION.INHERIT_SOURCE) {
    return {
      participation: eventKind.participation,
      cancellable: isCancellableEventKind(eventKind),
    }
  }
  const resolver = context.sourceEventContextResolver
  if (!resolver) {
    return failure(
      SYNC_EVENT_VIOLATION.SOURCE_CONTEXT_UNAVAILABLE,
      eventKind.id,
    )
  }
  try {
    const sourceContext: unknown = resolver(event)
    return isSourceEventContext(sourceContext)
      ? sourceContext
      : failure(SYNC_EVENT_VIOLATION.SOURCE_CONTEXT_UNAVAILABLE, eventKind.id)
  } catch {
    return failure(
      SYNC_EVENT_VIOLATION.SOURCE_CONTEXT_UNAVAILABLE,
      eventKind.id,
    )
  }
}

function isValidationFailure(
  value: SourceEventContext | SyncEventValidationFailure,
): value is SyncEventValidationFailure {
  return 'ok' in value && !value.ok
}

export function checkSyncEvent(
  event: SyncEvent,
  context: SyncEventValidationContext,
): SyncEventValidationResult {
  if (!SYNC_EVENT_PATH_SET.has(context.path)) {
    return failure(SYNC_EVENT_VIOLATION.ROUTE_KIND_MISMATCH, event.kind)
  }
  const eventKind = findEventKind(event.kind)
  if (!eventKind) {
    return failure(SYNC_EVENT_VIOLATION.UNKNOWN_KIND, event.kind)
  }
  if (!routeMatchesGroup(eventKind, context.path)) {
    return failure(SYNC_EVENT_VIOLATION.ROUTE_KIND_MISMATCH, eventKind.id)
  }

  const fields: unknown = event.fields
  if (!isFieldRecord(fields)) {
    return failure(SYNC_EVENT_VIOLATION.INVALID_FIELDS, eventKind.id)
  }
  for (const fieldKey of Reflect.ownKeys(fields)) {
    if (typeof fieldKey !== 'string' || !EVENT_SLOT_ID_SET.has(fieldKey)) {
      return failure(SYNC_EVENT_VIOLATION.UNKNOWN_SLOT, fieldKey)
    }
  }

  const kindContext = resolveKindContext(event, eventKind, context)
  if (isValidationFailure(kindContext)) {
    return kindContext
  }

  for (const rule of EVENT_FIELD_RULES) {
    if (!EVENT_SLOT_ID_SET.has(rule.id)) {
      continue
    }
    const slotId = rule.id as EventSlotId
    const hasSlot = Object.prototype.hasOwnProperty.call(fields, slotId)
    let presence
    try {
      presence = resolveEventFieldPresence(rule, {
        path: context.path,
        eventKind,
        participation: kindContext.participation,
        cancellable: kindContext.cancellable,
      })
    } catch {
      return failure(SYNC_EVENT_VIOLATION.INVALID_FIELD_CONDITION, slotId)
    }

    if (presence === EVENT_FIELD_PRESENCE.REQUIRED && !hasSlot) {
      return failure(SYNC_EVENT_VIOLATION.MISSING_SLOT, slotId)
    }
    if (presence === EVENT_FIELD_PRESENCE.FORBIDDEN && hasSlot) {
      return failure(SYNC_EVENT_VIOLATION.FORBIDDEN_SLOT, slotId)
    }
    if (
      hasSlot &&
      rule.shape.kind === 'composite' &&
      !isTargetEventReference(fields[slotId])
    ) {
      return failure(SYNC_EVENT_VIOLATION.INVALID_COMPOSITE, slotId)
    }
  }

  for (
    let leftIndex = 0;
    leftIndex < EVENT_IDENTIFIER_SLOT_IDS.length;
    leftIndex += 1
  ) {
    const leftSlot = EVENT_IDENTIFIER_SLOT_IDS[leftIndex]!
    if (!Object.prototype.hasOwnProperty.call(fields, leftSlot)) {
      continue
    }
    for (
      let rightIndex = leftIndex + 1;
      rightIndex < EVENT_IDENTIFIER_SLOT_IDS.length;
      rightIndex += 1
    ) {
      const rightSlot = EVENT_IDENTIFIER_SLOT_IDS[rightIndex]!
      if (
        Object.prototype.hasOwnProperty.call(fields, rightSlot) &&
        Object.is(fields[leftSlot], fields[rightSlot])
      ) {
        return failure(SYNC_EVENT_VIOLATION.IDENTIFIER_COLLISION, rightSlot)
      }
    }
  }

  return { ok: true }
}

export function validateSyncEvent(
  event: SyncEvent,
  context: SyncEventValidationContext,
): void {
  const result = checkSyncEvent(event, context)
  if (!result.ok) {
    throw new SyncEventValidationError(result.reason)
  }
}

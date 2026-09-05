// この投入境界は docs/design/sync-protocol.md 7-6 の U1 を表す。
// U3・U4・U6 は NFR-018 の単一実装対象であるため計算せず、状況計算の結果を注入で受け取る。

import {
  EVENT_FIELD_PRESENCE,
  EVENT_FIELD_RULES,
  EVENT_KIND_SLOT_ID,
  EVENT_SLOT_IDS,
  isCancellableEventKind,
  resolveEventFieldPresence,
  SYNC_EVENT_PATH,
  type EventFieldRule,
  type EventSlotId,
} from './eventFieldRules'
import { EVENT_KIND_RULES, type EventKind } from './eventKinds'
import type {
  DurableQueue,
  DurableQueueScope,
  DurableQueueSlot,
} from './durableQueue'
import type { SyncEvent, TargetEventReference } from './syncEvent'

type UndoQueue = Pick<DurableQueue, 'prepareAppend' | 'append'>

function findUndoEventKind(): EventKind {
  const eventKind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === 'undo',
  )
  if (!eventKind) {
    throw new Error('undo のイベント種別がありません')
  }
  return eventKind
}

const UNDO_EVENT_KIND = findUndoEventKind()
type CompositeFieldRule = Extract<
  EventFieldRule,
  { shape: { kind: 'composite' } }
>
const TARGET_REFERENCE_RULE = EVENT_FIELD_RULES.find(
  (rule): rule is CompositeFieldRule => rule.shape.kind === 'composite',
)
if (!TARGET_REFERENCE_RULE) {
  throw new Error('対象イベント参照の規則がありません')
}
const TARGET_REFERENCE_SLOT_ID = TARGET_REFERENCE_RULE.id

export type UndoOperationResolution<OperationResult = unknown> =
  | Readonly<{
      targetReference: TargetEventReference
      operationResult: OperationResult
    }>
  | Readonly<{
      targetReference?: undefined
      operationResult: OperationResult
    }>

export type UndoOperationResolver<OperationResult = unknown> = () =>
  UndoOperationResolution<OperationResult> | undefined

export type UndoQueueingInjections<OperationResult = unknown> = Readonly<{
  resolveUndoOperation?: UndoOperationResolver<OperationResult>
}>

export type UndoQueueingRequest = Readonly<{
  queue: UndoQueue
  scope: DurableQueueScope
  d5: unknown
  version: unknown
  event: SyncEvent
}>

export type UndoQueueingResult<OperationResult = unknown> = Readonly<{
  operationResult: OperationResult
  slot?: DurableQueueSlot
}>

function undoEvent(
  source: SyncEvent,
  targetReference: TargetEventReference,
): SyncEvent {
  const fields: SyncEvent['fields'] = {}
  const cancellable = isCancellableEventKind(UNDO_EVENT_KIND)

  for (const rule of EVENT_FIELD_RULES) {
    if (!EVENT_SLOT_IDS.includes(rule.id as EventSlotId)) {
      continue
    }
    const slotId = rule.id as EventSlotId
    const presence = resolveEventFieldPresence(rule, {
      path: SYNC_EVENT_PATH.P1,
      eventKind: UNDO_EVENT_KIND,
      participation: UNDO_EVENT_KIND.participation,
      cancellable,
    })
    if (
      presence !== EVENT_FIELD_PRESENCE.FORBIDDEN &&
      Object.prototype.hasOwnProperty.call(source.fields, slotId)
    ) {
      fields[slotId] = source.fields[slotId]
    }
  }

  fields[EVENT_KIND_SLOT_ID] = UNDO_EVENT_KIND.id
  fields[TARGET_REFERENCE_SLOT_ID] = targetReference
  return { fields }
}

export async function queueUndoEvent<OperationResult = unknown>(
  request: UndoQueueingRequest,
  injections: UndoQueueingInjections<OperationResult> = {},
): Promise<UndoQueueingResult<OperationResult> | undefined> {
  let resolution: UndoOperationResolution<OperationResult> | undefined
  try {
    resolution = injections.resolveUndoOperation?.()
  } catch {
    return undefined
  }
  if (!resolution) {
    return undefined
  }

  const { operationResult, targetReference } = resolution
  if (targetReference === undefined) {
    return Object.freeze({ operationResult })
  }

  const preparation = request.queue.prepareAppend({
    scope: request.scope,
    d5: request.d5,
    version: request.version,
    event: undoEvent(request.event, targetReference),
  })
  const slot = await request.queue.append(preparation)
  return Object.freeze({ operationResult, slot })
}

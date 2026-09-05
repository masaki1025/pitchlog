// この表と遷移判定は docs/design/sync-protocol.md 7-2 の写しである。
// 外部契約が未注入または確認不能なら状態を変えない。

import {
  CANON_ACK_STATE_RESULT,
  readCanonAckStateResults,
  type CanonAckStateResult,
} from './canonOracle'
import {
  DurableQueuePreparation,
  I6EvacuationReceipt,
  I6PersistenceReceipt,
} from './durableQueue'
import {
  actionRequiredLabelId,
  queueStateId,
  type I6AcceptedResult,
  type QueueActionRequiredLabel,
  type QueueStateId,
} from './queueState'

const UNSENT_STATE = queueStateId('未送信')
const ACTION_REQUIRED_STATE = queueStateId('要操作')
const SYNCED_STATE = queueStateId('同期済み')
const EVACUATED_STATE = queueStateId('退避済み')
const REVISION_ACTION_LABEL_ID = actionRequiredLabelId('改訂待ち')
const TOMBSTONE_ACTION_LABEL_ID = actionRequiredLabelId('墓標待ち')
const CONTENT_ACTION_LABEL_IDS = new Set<string>([
  REVISION_ACTION_LABEL_ID,
  TOMBSTONE_ACTION_LABEL_ID,
])
const O4_ACTION_LABEL_ID = actionRequiredLabelId('管理者対応待ち')

const CANON_ACK_RESULTS = readCanonAckStateResults()

function canonAckResultById(id: string): CanonAckStateResult {
  const result = CANON_ACK_RESULTS.find((candidate) => candidate.id === id)
  if (
    !result ||
    CANON_ACK_RESULTS.length !== Object.keys(CANON_ACK_STATE_RESULT).length
  ) {
    throw new Error('R-ACK-STATE の結果集合が不正です')
  }
  return result
}

const ACK_ACCEPTED_RESULT = canonAckResultById(CANON_ACK_STATE_RESULT.ACCEPTED)
const ACK_DUPLICATE_RESULT = canonAckResultById(
  CANON_ACK_STATE_RESULT.DUPLICATE,
)
const ACK_REJECTED_RESULT = canonAckResultById(CANON_ACK_STATE_RESULT.REJECTED)
const ACK_EVACUATED_RESULT = canonAckResultById(
  CANON_ACK_STATE_RESULT.EVACUATED,
)
const ACK_UNPROCESSED_RESULT = canonAckResultById(
  CANON_ACK_STATE_RESULT.UNPROCESSED,
)

const NO_QUEUE_STATE = '（なし）'
const P3_ACCEPTANCE_SOURCE = 'P3変更受理結果'
const DISCARD_TARGET = '破棄'

type QueueTransitionTrigger =
  | 'append-persisted'
  | 'apply-a5'
  | 'ack-unavailable'
  | 'action-replacement-persisted'
  | 'o4-retry-persisted'
  | 'p3-acceptance-persisted'
  | 'i6-evacuation-saved'
  | 'discard'

type QueueTransitionRuleDefinition = Readonly<{
  id: string
  source: QueueStateId | typeof NO_QUEUE_STATE | typeof P3_ACCEPTANCE_SOURCE
  target: QueueStateId | typeof DISCARD_TARGET
  trigger: QueueTransitionTrigger
  condition: Readonly<{
    kind: string
    a5ResultIds?: readonly string[]
  }>
  transitionAllowed: boolean
  changesState: boolean
}>

const QUEUE_TRANSITION_ROW_ID = {
  APPEND_PERSISTED: 'QT-01',
  A5_SYNCED: 'QT-02',
  A5_ACTION_REQUIRED: 'QT-03',
  A5_UNPROCESSED: 'QT-04',
  ACK_UNAVAILABLE: 'QT-05',
  ACTION_REPLACEMENT: 'QT-06',
  O4_RETRY: 'QT-07',
  A5_EVACUATED: 'QT-08',
  P3_ACCEPTANCE: 'QT-09',
  I6_EVACUATION: 'QT-10',
  UNSENT_DISCARD: 'QT-11',
  ACTION_REQUIRED_DISCARD: 'QT-12',
  SYNCED_DISCARD: 'QT-13',
  EVACUATED_DISCARD: 'QT-14',
} as const

export const QUEUE_TRANSITION_RULES = [
  {
    id: QUEUE_TRANSITION_ROW_ID.APPEND_PERSISTED,
    source: NO_QUEUE_STATE,
    target: UNSENT_STATE,
    trigger: 'append-persisted',
    condition: { kind: 'persistence-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.A5_SYNCED,
    source: UNSENT_STATE,
    target: SYNCED_STATE,
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: [ACK_ACCEPTED_RESULT.id, ACK_DUPLICATE_RESULT.id],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.A5_ACTION_REQUIRED,
    source: UNSENT_STATE,
    target: ACTION_REQUIRED_STATE,
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-rejection-with-b3-classification',
      a5ResultIds: [ACK_REJECTED_RESULT.id],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.A5_UNPROCESSED,
    source: UNSENT_STATE,
    target: UNSENT_STATE,
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: [ACK_UNPROCESSED_RESULT.id],
    },
    transitionAllowed: true,
    changesState: false,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.ACK_UNAVAILABLE,
    source: UNSENT_STATE,
    target: UNSENT_STATE,
    trigger: 'ack-unavailable',
    condition: { kind: 'ack-not-returned' },
    transitionAllowed: true,
    changesState: false,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.ACTION_REPLACEMENT,
    source: ACTION_REQUIRED_STATE,
    target: UNSENT_STATE,
    trigger: 'action-replacement-persisted',
    condition: { kind: 'same-slot-replacement-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.O4_RETRY,
    source: ACTION_REQUIRED_STATE,
    target: UNSENT_STATE,
    trigger: 'o4-retry-persisted',
    condition: {
      kind: 'o4-corrected-and-same-slot-replacement-completed',
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.A5_EVACUATED,
    source: UNSENT_STATE,
    target: EVACUATED_STATE,
    trigger: 'apply-a5',
    condition: {
      kind: 'a5-result',
      a5ResultIds: [ACK_EVACUATED_RESULT.id],
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.P3_ACCEPTANCE,
    source: P3_ACCEPTANCE_SOURCE,
    target: SYNCED_STATE,
    trigger: 'p3-acceptance-persisted',
    condition: {
      kind: 'accepted-at-resolved-and-device-persistence-completed',
    },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.I6_EVACUATION,
    source: SYNCED_STATE,
    target: EVACUATED_STATE,
    trigger: 'i6-evacuation-saved',
    condition: { kind: 'i6-evacuation-save-completed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.UNSENT_DISCARD,
    source: UNSENT_STATE,
    target: DISCARD_TARGET,
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.ACTION_REQUIRED_DISCARD,
    source: ACTION_REQUIRED_STATE,
    target: DISCARD_TARGET,
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.SYNCED_DISCARD,
    source: SYNCED_STATE,
    target: DISCARD_TARGET,
    trigger: 'discard',
    condition: { kind: 'retention-elapsed-and-rg1-inactive-confirmed' },
    transitionAllowed: true,
    changesState: true,
  },
  {
    id: QUEUE_TRANSITION_ROW_ID.EVACUATED_DISCARD,
    source: EVACUATED_STATE,
    target: DISCARD_TARGET,
    trigger: 'discard',
    condition: { kind: 'no-transition' },
    transitionAllowed: false,
    changesState: false,
  },
] as const satisfies readonly QueueTransitionRuleDefinition[]

export const QUEUE_TRANSITION_ROW_IDS = Object.freeze(
  QUEUE_TRANSITION_RULES.map((rule) => rule.id),
)

export type QueueTransitionRule = (typeof QUEUE_TRANSITION_RULES)[number]
export type QueueTransitionRowId = QueueTransitionRule['id']

const QUEUE_TRANSITION_RULE_BY_ID = new Map<
  QueueTransitionRowId,
  QueueTransitionRule
>(QUEUE_TRANSITION_RULES.map((rule) => [rule.id, rule]))

if (QUEUE_TRANSITION_RULE_BY_ID.size !== QUEUE_TRANSITION_RULES.length) {
  throw new Error('キュー遷移表の行 ID が重複しています')
}

export function queueTransitionRuleById(
  id: QueueTransitionRowId,
): QueueTransitionRule {
  const rule = QUEUE_TRANSITION_RULE_BY_ID.get(id)
  if (!rule) {
    throw new Error(`キュー遷移表の行 ID を解決できません: ${id}`)
  }
  return rule
}

export type QueueEventKey = Readonly<{
  d4: unknown
  d1: unknown
  d5: unknown
}>

type D1QueueSlot = Readonly<{
  state: QueueStateId
  source: 'd1-event'
  key: QueueEventKey
  content: unknown
  actionRequiredLabel?: QueueActionRequiredLabel['id']
}>

type P3QueueSlot = Readonly<
  I6AcceptedResult & {
    state: QueueStateId
    source: 'p3-acceptance'
  }
>

export type QueueSlot = D1QueueSlot | P3QueueSlot

type QueueSlotReplacement = Readonly<{
  key: QueueEventKey
  content: unknown
}>

export const B3_REASON_KIND = {
  CONTENT: '内容起因',
  O4: 'O4',
  UNKNOWN: '不明',
} as const

type ContentActionLabelId = Exclude<
  QueueActionRequiredLabel['id'],
  typeof O4_ACTION_LABEL_ID
>

export type B3ReasonClassification =
  | Readonly<{
      kind: typeof B3_REASON_KIND.CONTENT
      actionRequiredLabel: ContentActionLabelId
    }>
  | Readonly<{ kind: typeof B3_REASON_KIND.O4 }>
  | Readonly<{ kind: typeof B3_REASON_KIND.UNKNOWN }>

export const RG1_STATE = {
  ACTIVE: 'RG1中',
  INACTIVE_CONFIRMED: 'RG1中でないと確認済み',
  UNKNOWN: '確認不能',
} as const

export type Rg1State = (typeof RG1_STATE)[keyof typeof RG1_STATE]

export type QueueTransitionInjections = Readonly<{
  resolveA5?: (
    key: QueueEventKey,
  ) => Readonly<{ key: QueueEventKey; result: CanonAckStateResult }> | undefined
  classifyB3?: (
    input: Readonly<{
      slot: QueueSlot
      result: CanonAckStateResult
    }>,
  ) => B3ReasonClassification | undefined
  confirmTombstoneGeneration?: (input: {
    readonly slot: QueueSlot
    readonly replacement: QueueSlotReplacement
  }) => boolean | undefined
  confirmO4Correction?: (slot: QueueSlot) => boolean | undefined
  resolveRg1State?: (slot: QueueSlot) => Rg1State | undefined
}>

export type QueueTransitionRequest =
  | Readonly<{
      kind: 'append-persisted'
      key: QueueEventKey
      content: unknown
    }>
  | Readonly<{
      kind: 'apply-a5'
      preparation: DurableQueuePreparation<'a5-transition'>
    }>
  | Readonly<{ kind: 'ack-unavailable'; slot: QueueSlot }>
  | Readonly<{
      kind: 'action-replacement-persisted'
      slot: QueueSlot
      replacement: QueueSlotReplacement
    }>
  | Readonly<{
      kind: 'o4-retry-persisted'
      slot: QueueSlot
      replacement: QueueSlotReplacement
    }>
  | Readonly<{
      kind: 'p3-acceptance-persisted'
      persistenceReceipt?: I6PersistenceReceipt
    }>
  | Readonly<{
      kind: 'i6-evacuation-saved'
      evacuationReceipt?: I6EvacuationReceipt
    }>
  | Readonly<{
      kind: 'discard'
      slot: QueueSlot
      confirmed24HoursElapsed: boolean
    }>

export type QueueTransitionResult =
  | Readonly<{
      applied: false
      rowId?: QueueTransitionRowId
    }>
  | Readonly<{
      applied: true
      rowId: QueueTransitionRowId
      target: QueueStateId | typeof DISCARD_TARGET
      slot?: QueueSlot
    }>

function notApplied(rowId?: QueueTransitionRowId): QueueTransitionResult {
  return rowId ? { applied: false, rowId } : { applied: false }
}

function applySlotRule(
  rule: QueueTransitionRule,
  slot: QueueSlot,
): QueueTransitionResult {
  if (!rule.transitionAllowed || rule.target === DISCARD_TARGET) {
    return notApplied(rule.id)
  }
  return {
    applied: true,
    rowId: rule.id,
    target: rule.target,
    slot: { ...slot, state: rule.target },
  }
}

function ruleAcceptsA5Result(
  rule: QueueTransitionRuleDefinition,
  result: CanonAckStateResult,
): boolean {
  return rule.condition.a5ResultIds?.includes(result.id) ?? false
}

function sameEventKey(first: QueueEventKey, second: QueueEventKey): boolean {
  return (
    Object.is(first.d4, second.d4) &&
    Object.is(first.d1, second.d1) &&
    Object.is(first.d5, second.d5)
  )
}

function sameSlotWithNewD5(
  slot: D1QueueSlot,
  replacement: QueueSlotReplacement,
): boolean {
  return (
    Object.is(slot.key.d4, replacement.key.d4) &&
    Object.is(slot.key.d1, replacement.key.d1) &&
    !Object.is(slot.key.d5, replacement.key.d5)
  )
}

function replacedUnsentSlot(
  slot: D1QueueSlot,
  replacement: QueueSlotReplacement,
): QueueSlot {
  return {
    state: UNSENT_STATE,
    key: replacement.key,
    content: replacement.content,
    source: slot.source,
  }
}

function hasEmptyContent(content: unknown): boolean {
  return (
    typeof content === 'object' &&
    content !== null &&
    Reflect.ownKeys(content).length === 0
  )
}

function applyA5(
  request: Extract<QueueTransitionRequest, { kind: 'apply-a5' }>,
  injections: QueueTransitionInjections,
): QueueTransitionResult {
  const snapshot = DurableQueuePreparation.consumeA5(request.preparation)
  if (!snapshot) {
    return notApplied()
  }
  const { slot } = snapshot

  let resolved:
    Readonly<{ key: QueueEventKey; result: CanonAckStateResult }> | undefined
  try {
    resolved = injections.resolveA5?.(slot.key)
  } catch {
    return notApplied()
  }
  if (!resolved || !sameEventKey(slot.key, resolved.key)) {
    return notApplied()
  }

  const syncedRule = queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.A5_SYNCED)
  const unprocessedRule = queueTransitionRuleById(
    QUEUE_TRANSITION_ROW_ID.A5_UNPROCESSED,
  )
  const evacuatedRule = queueTransitionRuleById(
    QUEUE_TRANSITION_ROW_ID.A5_EVACUATED,
  )
  const actionRequiredRule = queueTransitionRuleById(
    QUEUE_TRANSITION_ROW_ID.A5_ACTION_REQUIRED,
  )

  if (ruleAcceptsA5Result(syncedRule, resolved.result)) {
    if (!snapshot.allowsSyncedTransition) {
      return notApplied(syncedRule.id)
    }
    return applySlotRule(syncedRule, slot)
  }
  if (ruleAcceptsA5Result(unprocessedRule, resolved.result)) {
    return applySlotRule(unprocessedRule, slot)
  }
  if (ruleAcceptsA5Result(evacuatedRule, resolved.result)) {
    return applySlotRule(evacuatedRule, slot)
  }
  if (!ruleAcceptsA5Result(actionRequiredRule, resolved.result)) {
    return notApplied()
  }

  let classification: B3ReasonClassification | undefined
  try {
    classification = injections.classifyB3?.({
      slot,
      result: resolved.result,
    })
  } catch {
    return notApplied(actionRequiredRule.id)
  }
  if (!classification || classification.kind === B3_REASON_KIND.UNKNOWN) {
    return notApplied(actionRequiredRule.id)
  }

  let actionRequiredLabel: QueueActionRequiredLabel['id']
  if (classification.kind === B3_REASON_KIND.O4) {
    actionRequiredLabel = O4_ACTION_LABEL_ID
  } else if (CONTENT_ACTION_LABEL_IDS.has(classification.actionRequiredLabel)) {
    actionRequiredLabel = classification.actionRequiredLabel
  } else {
    return notApplied(actionRequiredRule.id)
  }

  return applySlotRule(actionRequiredRule, {
    ...slot,
    actionRequiredLabel,
  })
}

function applyActionReplacement(
  request: Extract<
    QueueTransitionRequest,
    { kind: 'action-replacement-persisted' }
  >,
  injections: QueueTransitionInjections,
): QueueTransitionResult {
  const { slot, replacement } = request
  const rule = queueTransitionRuleById(
    QUEUE_TRANSITION_ROW_ID.ACTION_REPLACEMENT,
  )
  if (
    slot.source !== 'd1-event' ||
    slot.state !== ACTION_REQUIRED_STATE ||
    !slot.actionRequiredLabel ||
    !CONTENT_ACTION_LABEL_IDS.has(slot.actionRequiredLabel) ||
    !sameSlotWithNewD5(slot, replacement)
  ) {
    return notApplied(rule.id)
  }

  if (slot.actionRequiredLabel === TOMBSTONE_ACTION_LABEL_ID) {
    let confirmed: boolean | undefined
    try {
      if (!hasEmptyContent(replacement.content)) {
        return notApplied(rule.id)
      }
      confirmed = injections.confirmTombstoneGeneration?.({
        slot,
        replacement,
      })
    } catch {
      return notApplied(rule.id)
    }
    if (confirmed !== true) {
      return notApplied(rule.id)
    }
  }
  return applySlotRule(rule, replacedUnsentSlot(slot, replacement))
}

function applyO4Retry(
  request: Extract<QueueTransitionRequest, { kind: 'o4-retry-persisted' }>,
  injections: QueueTransitionInjections,
): QueueTransitionResult {
  const { slot, replacement } = request
  const rule = queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.O4_RETRY)
  if (
    slot.source !== 'd1-event' ||
    slot.state !== ACTION_REQUIRED_STATE ||
    slot.actionRequiredLabel !== O4_ACTION_LABEL_ID ||
    !sameSlotWithNewD5(slot, replacement) ||
    !Object.is(slot.content, replacement.content)
  ) {
    return notApplied(rule.id)
  }

  let confirmed: boolean | undefined
  try {
    confirmed = injections.confirmO4Correction?.(slot)
  } catch {
    return notApplied(rule.id)
  }
  if (confirmed !== true) {
    return notApplied(rule.id)
  }
  return applySlotRule(rule, replacedUnsentSlot(slot, replacement))
}

function applyP3Acceptance(
  request: Extract<QueueTransitionRequest, { kind: 'p3-acceptance-persisted' }>,
): QueueTransitionResult {
  const rule = queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.P3_ACCEPTANCE)
  const slot = I6PersistenceReceipt.verify(request.persistenceReceipt)
  if (!slot || slot.state !== SYNCED_STATE) {
    return notApplied(rule.id)
  }
  return applySlotRule(rule, slot)
}

function applyI6Evacuation(
  receipt: I6EvacuationReceipt | undefined,
): QueueTransitionResult {
  const rule = queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.I6_EVACUATION)
  const slot = I6EvacuationReceipt.verify(receipt)
  if (!slot || slot.state !== SYNCED_STATE || slot.source !== 'p3-acceptance') {
    return notApplied(rule.id)
  }
  return applySlotRule(rule, slot)
}

function applyDiscard(
  request: Extract<QueueTransitionRequest, { kind: 'discard' }>,
  injections: QueueTransitionInjections,
): QueueTransitionResult {
  const { slot } = request
  if (slot.state === UNSENT_STATE) {
    return notApplied(
      queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.UNSENT_DISCARD).id,
    )
  }
  if (slot.state === ACTION_REQUIRED_STATE) {
    return notApplied(
      queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.ACTION_REQUIRED_DISCARD)
        .id,
    )
  }
  if (slot.state === EVACUATED_STATE) {
    return notApplied(
      queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.EVACUATED_DISCARD).id,
    )
  }
  const rule = queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.SYNCED_DISCARD)
  if (slot.state !== SYNCED_STATE || !request.confirmed24HoursElapsed) {
    return notApplied(rule.id)
  }

  let rg1State: Rg1State | undefined
  try {
    rg1State = injections.resolveRg1State?.(slot)
  } catch {
    return notApplied(rule.id)
  }
  if (rg1State !== RG1_STATE.INACTIVE_CONFIRMED) {
    return notApplied(rule.id)
  }
  return {
    applied: true,
    rowId: rule.id,
    target: DISCARD_TARGET,
  }
}

export function evaluateQueueTransition(
  request: QueueTransitionRequest,
  injections: QueueTransitionInjections = {},
): QueueTransitionResult {
  switch (request.kind) {
    case 'append-persisted':
      return applySlotRule(
        queueTransitionRuleById(QUEUE_TRANSITION_ROW_ID.APPEND_PERSISTED),
        {
          state: UNSENT_STATE,
          key: request.key,
          content: request.content,
          source: 'd1-event',
        },
      )
    case 'apply-a5':
      return applyA5(request, injections)
    case 'ack-unavailable': {
      const ackUnavailableRule = queueTransitionRuleById(
        QUEUE_TRANSITION_ROW_ID.ACK_UNAVAILABLE,
      )
      return request.slot.source === 'd1-event' &&
        request.slot.state === UNSENT_STATE
        ? applySlotRule(ackUnavailableRule, request.slot)
        : notApplied(ackUnavailableRule.id)
    }
    case 'action-replacement-persisted':
      return applyActionReplacement(request, injections)
    case 'o4-retry-persisted':
      return applyO4Retry(request, injections)
    case 'p3-acceptance-persisted':
      return applyP3Acceptance(request)
    case 'i6-evacuation-saved':
      return applyI6Evacuation(request.evacuationReceipt)
    case 'discard':
      return applyDiscard(request, injections)
  }
}

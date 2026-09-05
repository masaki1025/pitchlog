// この規律は docs/design/sync-protocol.md 7-4 の Q3・Q7 と、
// docs/features/sync-queue-lifecycle/plan.md 4 節の清掃トリガの実装である。

import type {
  DurableQueue,
  DurableQueueAppend,
  DurableQueueSlot,
} from './durableQueue'
import {
  evaluateQueueTransition,
  RG1_STATE,
  type QueueSlot,
  type Rg1State,
} from './queueTransition'

export const DEFAULT_UNSENT_WARNING_THRESHOLD = 350

export const CLIENT_DISCIPLINE_RULES = [{ id: 'Q3' }, { id: 'Q7' }] as const

export type ClientDisciplineRule = (typeof CLIENT_DISCIPLINE_RULES)[number]

export type QueueAppendDisciplineResult = Readonly<{
  slot: DurableQueueSlot
  unsentCount: number
  warningThresholdReached: boolean
  recordingBlocked: false
}>

export async function appendUnderQueueDiscipline(
  queue: Pick<DurableQueue, 'append' | 'countUnsentSlots'>,
  input: DurableQueueAppend,
  warningThreshold = DEFAULT_UNSENT_WARNING_THRESHOLD,
): Promise<QueueAppendDisciplineResult> {
  const slot = await queue.append(input)
  const unsentCount = await queue.countUnsentSlots()

  return {
    slot,
    unsentCount,
    warningThresholdReached: unsentCount >= warningThreshold,
    recordingBlocked: false,
  }
}

export type AuthenticationContinuityInjections = Readonly<{
  resolveAuthenticationExpired?: () => boolean | undefined
  resumeSynchronization?: () => void | Promise<void>
}>

export type AuthenticationContinuityResult = Readonly<{
  authenticationExpired: boolean | undefined
  synchronizationResumed: boolean
}>

export async function coordinateAuthenticationSync(
  injections: AuthenticationContinuityInjections = {},
): Promise<AuthenticationContinuityResult> {
  let authenticationExpired: boolean | undefined
  try {
    authenticationExpired = injections.resolveAuthenticationExpired?.()
  } catch {
    return {
      authenticationExpired: undefined,
      synchronizationResumed: false,
    }
  }

  if (authenticationExpired !== false || !injections.resumeSynchronization) {
    return {
      authenticationExpired,
      synchronizationResumed: false,
    }
  }

  try {
    await injections.resumeSynchronization()
  } catch {
    return {
      authenticationExpired,
      synchronizationResumed: false,
    }
  }
  return {
    authenticationExpired,
    synchronizationResumed: true,
  }
}

export const CLIENT_CLEANUP_TRIGGER = {
  DEVICE_STARTUP: '端末起動時',
  EXPLICIT_REQUEST: '明示的な清掃要求',
} as const

export type ClientCleanupTrigger =
  (typeof CLIENT_CLEANUP_TRIGGER)[keyof typeof CLIENT_CLEANUP_TRIGGER]

export type QueueCleanupCandidate = Readonly<{
  slot: QueueSlot
  confirmed24HoursElapsed: boolean
}>

export type QueueCleanupSelector = () =>
  readonly QueueCleanupCandidate[] | Promise<readonly QueueCleanupCandidate[]>

export type ClientCleanupInjections = Readonly<{
  resolveRg1State?: () => Rg1State | undefined | Promise<Rg1State | undefined>
  selectCleanupCandidates?: QueueCleanupSelector
}>

export type ClientCleanupPlan = Readonly<{
  trigger: ClientCleanupTrigger
  rg1State: Rg1State | undefined
  selectionStarted: boolean
  discardCandidates: readonly QueueCleanupCandidate[]
}>

function deferredCleanupPlan(
  trigger: ClientCleanupTrigger,
  rg1State: Rg1State | undefined,
): ClientCleanupPlan {
  return {
    trigger,
    rg1State,
    selectionStarted: false,
    discardCandidates: [],
  }
}

function isClientCleanupTrigger(value: unknown): value is ClientCleanupTrigger {
  return Object.values(CLIENT_CLEANUP_TRIGGER).some(
    (trigger) => trigger === value,
  )
}

export async function planQueueCleanup(
  trigger: ClientCleanupTrigger,
  injections: ClientCleanupInjections = {},
): Promise<ClientCleanupPlan> {
  if (!isClientCleanupTrigger(trigger)) {
    return deferredCleanupPlan(trigger, undefined)
  }

  let rg1State: Rg1State | undefined
  try {
    rg1State = await injections.resolveRg1State?.()
  } catch {
    return deferredCleanupPlan(trigger, undefined)
  }
  if (rg1State !== RG1_STATE.INACTIVE_CONFIRMED) {
    return deferredCleanupPlan(trigger, rg1State)
  }

  let candidates: readonly QueueCleanupCandidate[]
  try {
    const selectCleanupCandidates = injections.selectCleanupCandidates
    if (!selectCleanupCandidates) {
      return deferredCleanupPlan(trigger, rg1State)
    }
    candidates = await selectCleanupCandidates()
  } catch {
    return deferredCleanupPlan(trigger, rg1State)
  }

  const discardCandidates = candidates.filter(
    (candidate) =>
      evaluateQueueTransition(
        {
          kind: 'discard',
          slot: candidate.slot,
          confirmed24HoursElapsed: candidate.confirmed24HoursElapsed,
        },
        { resolveRg1State: () => rg1State },
      ).applied,
  )

  return {
    trigger,
    rg1State,
    selectionStarted: true,
    discardCandidates,
  }
}

// この排他境界は docs/design/sync-protocol.md 7-4 の Q2 系規律と、
// docs/features/sync-queue-lifecycle/plan.md 4 節の単一書き手機構の実装である。

import { createSyncNotice, type SyncNoticeDescriptor } from './syncNotices'

export const SINGLE_WRITER_PRECONDITION_IDS = [
  'topLevelHttps',
  'sameBrowserProfile',
  'sameBrowsingMode',
  'sameStorageBucket',
  'siteStorageAvailable',
  'lockdownModeNotApplied',
] as const

export type SingleWriterPreconditionId =
  (typeof SINGLE_WRITER_PRECONDITION_IDS)[number]

export type SingleWriterPreconditions = Readonly<
  Record<SingleWriterPreconditionId, boolean>
>

export type ExclusiveLockManager = Readonly<{
  request: <Result>(
    name: string,
    callback: (lock: unknown) => Result | PromiseLike<Result>,
  ) => Promise<Result>
}>

export type SingleWriterRequest = Readonly<{
  gameIdentifier: string
}>

export type SingleWriterRevalidationContext = Readonly<{
  gameIdentifier: string
  lockName: string
  lock: unknown
}>

export type SingleWriterInjections = Readonly<{
  resolvePreconditions?: () =>
    | SingleWriterPreconditions
    | undefined
    | Promise<SingleWriterPreconditions | undefined>
  revalidateSingleWriter?: (
    context: SingleWriterRevalidationContext,
  ) => boolean | undefined | Promise<boolean | undefined>
  lockManager?: ExclusiveLockManager | null
}>

export const SINGLE_WRITER_START_FAILURE = {
  PRECONDITIONS_NOT_CONFIRMED: 'preconditions-not-confirmed',
  LOCK_MANAGER_UNAVAILABLE: 'lock-manager-unavailable',
  LOCK_REQUEST_FAILED: 'lock-request-failed',
  REVALIDATION_FAILED: 'revalidation-failed',
} as const

export type SingleWriterStartFailure =
  (typeof SINGLE_WRITER_START_FAILURE)[keyof typeof SINGLE_WRITER_START_FAILURE]

export type SingleWriterResult<Result> =
  | Readonly<{
      recordingStarted: false
      reason: SingleWriterStartFailure
    }>
  | Readonly<{
      recordingStarted: true
      value: Result
    }>

export const NON_OWNER_INPUT_REASON = {
  NOT_ACCEPTED: '受理していない',
  ACCEPTED_OPERATION_LOST: '受理済み操作の喪失',
} as const

export type NonOwnerInputRejection = Readonly<{
  accepted: false
  reason: typeof NON_OWNER_INPUT_REASON.NOT_ACCEPTED
  notice: SyncNoticeDescriptor<'Q2-b'>
}>

function notStarted(
  reason: SingleWriterStartFailure,
): SingleWriterResult<never> {
  return { recordingStarted: false, reason }
}

function browserLockManager(): ExclusiveLockManager | undefined {
  if (typeof navigator === 'undefined' || !navigator.locks) {
    return undefined
  }
  return navigator.locks as ExclusiveLockManager
}

function allPreconditionsConfirmed(
  preconditions: SingleWriterPreconditions,
): boolean {
  return SINGLE_WRITER_PRECONDITION_IDS.every(
    (id) => preconditions[id] === true,
  )
}

export function singleWriterLockName(gameIdentifier: string): string {
  return `pitchlog:game:${gameIdentifier}`
}

export async function runAsSingleWriter<Result>(
  request: SingleWriterRequest,
  operation: () => Result | Promise<Result>,
  injections: SingleWriterInjections = {},
): Promise<SingleWriterResult<Result>> {
  let preconditions: SingleWriterPreconditions | undefined
  try {
    preconditions = await injections.resolvePreconditions?.()
  } catch {
    return notStarted(SINGLE_WRITER_START_FAILURE.PRECONDITIONS_NOT_CONFIRMED)
  }
  if (!preconditions || !allPreconditionsConfirmed(preconditions)) {
    return notStarted(SINGLE_WRITER_START_FAILURE.PRECONDITIONS_NOT_CONFIRMED)
  }

  const lockManager =
    injections.lockManager === undefined
      ? browserLockManager()
      : injections.lockManager
  if (!lockManager) {
    return notStarted(SINGLE_WRITER_START_FAILURE.LOCK_MANAGER_UNAVAILABLE)
  }

  const lockName = singleWriterLockName(request.gameIdentifier)
  let recordingStarted = false
  try {
    return await lockManager.request(lockName, async (lock) => {
      if (lock === null || lock === undefined) {
        return notStarted(SINGLE_WRITER_START_FAILURE.LOCK_REQUEST_FAILED)
      }

      let revalidated: boolean | undefined
      try {
        revalidated = await injections.revalidateSingleWriter?.({
          gameIdentifier: request.gameIdentifier,
          lockName,
          lock,
        })
      } catch {
        return notStarted(SINGLE_WRITER_START_FAILURE.REVALIDATION_FAILED)
      }
      if (revalidated !== true) {
        return notStarted(SINGLE_WRITER_START_FAILURE.REVALIDATION_FAILED)
      }

      recordingStarted = true
      const value = await operation()
      return { recordingStarted: true, value }
    })
  } catch (error) {
    if (recordingStarted) {
      throw error
    }
    return notStarted(SINGLE_WRITER_START_FAILURE.LOCK_REQUEST_FAILED)
  }
}

export function rejectNonOwnerInput(): NonOwnerInputRejection {
  return {
    accepted: false,
    reason: NON_OWNER_INPUT_REASON.NOT_ACCEPTED,
    notice: createSyncNotice('Q2-b', {}),
  }
}

import 'fake-indexeddb/auto'

import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { appendUnderQueueDiscipline } from '../lib/sync/clientDiscipline'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
} from '../lib/sync/durableQueue'
import { EVENT_SLOT_IDS } from '../lib/sync/eventFieldRules'
import {
  FAILURE_SCENARIO_IDS,
  parseFailureScenarioContract,
  type FailureScenarioContract,
  type FailureScenarioField,
  type FailureScenarioObservation,
  type FailureScenarioResult,
} from '../lib/sync/failureScenarioContract'
import {
  rejectNonOwnerInput,
  runAsSingleWriter,
  singleWriterLockName,
  SINGLE_WRITER_PRECONDITION_IDS,
  type ExclusiveLockManager,
  type SingleWriterPreconditions,
} from '../lib/sync/singleWriter'

export const FAILURE_FIXTURE_DIRECTORY = resolve(
  cwd(),
  '../tests/fixtures/sync-protocol-failures',
)

export type FailureScenarioExecutionOptions = Readonly<{
  extraPersistence?: boolean
}>

type JsonRecord = Record<string, unknown>
type Deferred = Readonly<{
  promise: Promise<void>
  resolve: () => void
}>
type QueueSnapshot = Readonly<{
  count: number
  nextD1: number
}>
type ScenarioContext = Readonly<{
  contract: FailureScenarioContract
  queue: DurableQueue
  scope: DurableQueueScope
  initial: QueueSnapshot
  locks: MockWebLocks
  options: FailureScenarioExecutionOptions
}>
type ScenarioRunner = (
  context: ScenarioContext,
) => Promise<FailureScenarioResult>

const CONFIRMED_PRECONDITIONS = Object.fromEntries(
  SINGLE_WRITER_PRECONDITION_IDS.map((id) => [id, Boolean(id)]),
) as unknown as SingleWriterPreconditions

const [
  MULTI_TAB_SINGLE_WRITER,
  LEADER_FREEZE_REELECTION,
  WAITING_INPUT_NOT_ACCEPTED,
  DURABLE_APPEND_FAILURE,
] = FAILURE_SCENARIO_IDS

const allocatedDatabaseNames: string[] = []

function deferred(): Deferred {
  let resolvePromise: (() => void) | undefined
  const promise = new Promise<void>((resolvePromiseValue) => {
    resolvePromise = resolvePromiseValue
  })
  if (!resolvePromise) {
    throw new Error('待機制御を初期化できません')
  }
  return { promise, resolve: resolvePromise }
}

function requireRecord(value: unknown, location: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${location} はオブジェクトでなければなりません`)
  }
  return value as JsonRecord
}

function fieldValue(
  section: Readonly<Record<string, FailureScenarioField>>,
  fieldId: string,
): unknown {
  const field = requireRecord(section[fieldId], fieldId)
  if (!Object.hasOwn(field, 'value')) {
    throw new Error(`${fieldId} に実行用の値がありません`)
  }
  return field.value
}

function recordFieldValue(
  section: Readonly<Record<string, FailureScenarioField>>,
  fieldId: string,
): JsonRecord {
  return requireRecord(fieldValue(section, fieldId), fieldId)
}

function numberProperty(record: JsonRecord, property: string): number {
  const value = record[property]
  if (
    typeof value !== 'number' ||
    !Number.isInteger(value) ||
    value < [].length
  ) {
    throw new Error(`${property} は非負整数でなければなりません`)
  }
  return value
}

function booleanProperty(record: JsonRecord, property: string): boolean {
  const value = record[property]
  if (typeof value !== 'boolean') {
    throw new Error(`${property} は真偽値でなければなりません`)
  }
  return value
}

function stringArrayProperty(
  record: JsonRecord,
  property: string,
): readonly string[] {
  const value = record[property]
  if (
    !Array.isArray(value) ||
    !value.length ||
    !value.every((item) => typeof item === 'string' && item)
  ) {
    throw new Error(`${property} は空でない文字列配列でなければなりません`)
  }
  return value as string[]
}

function scenarioContexts(
  contract: FailureScenarioContract,
): readonly [string, string] {
  const tabs = recordFieldValue(contract.input, 'tabs')
  const [primary, secondary, ...extra] = stringArrayProperty(tabs, 'contexts')
  if (!primary || !secondary || extra.length) {
    throw new Error('シナリオには二つのタブ文脈が必要です')
  }
  return [primary, secondary]
}

function observationPoints(
  contract: FailureScenarioContract,
): readonly string[] {
  return [
    ...new Set(
      contract.comparisonUnit.map((comparison) => comparison.observationPoint),
    ),
  ]
}

function singleObservationPoint(contract: FailureScenarioContract): string {
  const [point, ...extra] = observationPoints(contract)
  if (!point || extra.length) {
    throw new Error('シナリオの観測点は一つでなければなりません')
  }
  return point
}

function pairedObservationPoints(
  contract: FailureScenarioContract,
): readonly [string, string] {
  const [before, after, ...extra] = observationPoints(contract)
  if (!before || !after || extra.length) {
    throw new Error('シナリオの観測点は二つでなければなりません')
  }
  return [before, after]
}

function appendInput(
  scope: DurableQueueScope,
  marker: unknown,
): DurableQueueAppend {
  return {
    scope,
    d5: { marker },
    version: { marker },
    event: { fields: {} },
  }
}

async function queueSnapshot(
  queue: DurableQueue,
  scope: DurableQueueScope,
): Promise<QueueSnapshot> {
  const [count, nextD1] = await Promise.all([
    queue.countSlots(),
    queue.readNextD1(scope),
  ])
  return { count, nextD1 }
}

function observation(
  observationPoint: string,
  fields: FailureScenarioObservation['fields'],
): FailureScenarioObservation {
  return { observationPoint, fields }
}

function confirmedInjections(
  lockManager: ExclusiveLockManager,
  onRevalidation?: () => void,
) {
  return {
    lockManager,
    resolvePreconditions: () => CONFIRMED_PRECONDITIONS,
    revalidateSingleWriter: (context: { lock: unknown }) => {
      onRevalidation?.()
      return Boolean(context.lock)
    },
  }
}

class MockWebLocks {
  readonly #tails = new Map<string, Promise<void>>()
  readonly #owners = new Map<string, string>()

  managerFor(owner: string, onRequest?: () => void): ExclusiveLockManager {
    return {
      request: async <Result>(
        name: string,
        callback: (lock: unknown) => Result | PromiseLike<Result>,
      ): Promise<Result> => {
        onRequest?.()
        const predecessor = this.#tails.get(name) ?? Promise.resolve()
        let release: (() => void) | undefined
        const turn = new Promise<void>((resolveTurn) => {
          release = resolveTurn
        })
        this.#tails.set(name, turn)

        await predecessor
        this.#owners.set(name, owner)
        try {
          return await callback({ name, owner })
        } finally {
          if (this.#owners.get(name) === owner) {
            this.#owners.delete(name)
          }
          release?.()
          if (this.#tails.get(name) === turn) {
            this.#tails.delete(name)
          }
        }
      },
    }
  }

  owner(name: string): string | undefined {
    return this.#owners.get(name)
  }

  ownerCount(name: string): number {
    const owner = this.owner(name)
    return [owner].filter(
      (candidate): candidate is string => candidate !== undefined,
    ).length
  }
}

async function runMultiTabSingleWriter(
  context: ScenarioContext,
): Promise<FailureScenarioResult> {
  const { contract, queue, scope, initial, locks } = context
  const [primary, secondary] = scenarioContexts(contract)
  const point = singleObservationPoint(contract)
  const lockName = singleWriterLockName(String(scope.game))
  const primaryStarted = deferred()
  const releasePrimary = deferred()
  const secondaryRequested = deferred()
  const appendedD1s: number[] = []

  const primaryOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    async () => {
      const append = await appendUnderQueueDiscipline(
        queue,
        appendInput(scope, primary),
      )
      appendedD1s.push(append.slot.d1)
      primaryStarted.resolve()
      await releasePrimary.promise
      return append
    },
    confirmedInjections(locks.managerFor(primary)),
  )
  await primaryStarted.promise

  const secondaryOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    () => secondary,
    confirmedInjections(
      locks.managerFor(secondary, secondaryRequested.resolve),
    ),
  )
  await secondaryRequested.promise
  const rejection = rejectNonOwnerInput()
  const ownerCount = locks.ownerCount(lockName)

  releasePrimary.resolve()
  const [primaryResult, secondaryResult] = await Promise.all([
    primaryOperation,
    secondaryOperation,
  ])
  const final = await queueSnapshot(queue, scope)
  const acceptedTabCount = [
    primaryResult.recordingStarted,
    rejection.accepted,
  ].filter(Boolean).length

  return {
    scenarioId: contract.scenarioId,
    observations: [
      observation(point, {
        queue: { appendCount: final.count - initial.count },
        d1: {
          duplicateCount: appendedD1s.length - new Set(appendedD1s).size,
        },
        lock: {
          ownerCount,
          nonOwnerReadOnly: !rejection.accepted,
        },
        acceptanceDisplay: {
          acceptedTabCount,
          nonOwnerNoticeId: rejection.notice.noticeId,
        },
        reinputAvailability: {
          nonOwnerInputAccepted: rejection.accepted,
          retryAfterLockAcquisition: secondaryResult.recordingStarted,
        },
      }),
    ],
  }
}

async function runLeaderFreezeReelection(
  context: ScenarioContext,
): Promise<FailureScenarioResult> {
  const { contract, queue, scope, initial, locks } = context
  const [primary, waiting] = scenarioContexts(contract)
  const [beforePoint, afterPoint] = pairedObservationPoints(contract)
  const tabs = recordFieldValue(contract.input, 'tabs')
  const terminationPathUsed = booleanProperty(
    tabs,
    'waitingTabUsesTerminationPath',
  )
  const lockName = singleWriterLockName(String(scope.game))
  const primaryStarted = deferred()
  const releasePrimary = deferred()
  const waitingRequested = deferred()
  const waitingStarted = deferred()
  const releaseWaiting = deferred()
  const waitingRevalidations: unknown[] = []
  const waitingOperations: unknown[] = []

  const primaryOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    async () => {
      primaryStarted.resolve()
      await releasePrimary.promise
    },
    confirmedInjections(locks.managerFor(primary)),
  )
  await primaryStarted.promise

  const waitingOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    async () => {
      waitingOperations.push(waiting)
      waitingStarted.resolve()
      await releaseWaiting.promise
    },
    confirmedInjections(
      locks.managerFor(waiting, waitingRequested.resolve),
      () => waitingRevalidations.push(waiting),
    ),
  )
  await waitingRequested.promise

  const before = await queueSnapshot(queue, scope)
  const ownerBeforeTermination = locks.owner(lockName)
  const waitingShownBeforeTermination = Boolean(waitingOperations.length)

  releasePrimary.resolve()
  await primaryOperation
  await waitingStarted.promise

  const after = await queueSnapshot(queue, scope)
  const ownerAfterReelection = locks.owner(lockName)
  const revalidatedBeforeResume =
    Boolean(waitingRevalidations.length) && Boolean(waitingOperations.length)

  releaseWaiting.resolve()
  const waitingResult = await waitingOperation
  const recordingResumed =
    revalidatedBeforeResume &&
    ownerAfterReelection === waiting &&
    waitingResult.recordingStarted

  return {
    scenarioId: contract.scenarioId,
    observations: [
      observation(beforePoint, {
        queue: {
          unchanged: before.count === initial.count,
          count: before.count,
        },
        d1: {
          unchanged: before.nextD1 === initial.nextD1,
          next: before.nextD1,
        },
        lock: {
          owner: ownerBeforeTermination,
          forciblyAcquired: ownerBeforeTermination === waiting,
        },
        acceptanceDisplay: {
          waitingInputShownAsAccepted: waitingShownBeforeTermination,
        },
        reinputAvailability: { required: !terminationPathUsed },
      }),
      observation(afterPoint, {
        queue: {
          unchanged: after.count === initial.count,
          count: after.count,
        },
        d1: {
          unchanged: after.nextD1 === initial.nextD1,
          next: after.nextD1,
        },
        lock: {
          owner: ownerAfterReelection,
          singleWriterRevalidated: revalidatedBeforeResume,
        },
        acceptanceDisplay: {
          recordingResumedAfterRevalidation: recordingResumed,
        },
        reinputAvailability: { required: !terminationPathUsed },
      }),
    ],
  }
}

async function runWaitingInputNotAccepted(
  context: ScenarioContext,
): Promise<FailureScenarioResult> {
  const { contract, queue, scope, initial, locks } = context
  const [primary, waiting] = scenarioContexts(contract)
  const point = singleObservationPoint(contract)
  const lockName = singleWriterLockName(String(scope.game))
  const primaryStarted = deferred()
  const releasePrimary = deferred()
  const waitingRequested = deferred()

  const primaryOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    async () => {
      primaryStarted.resolve()
      await releasePrimary.promise
    },
    confirmedInjections(locks.managerFor(primary)),
  )
  await primaryStarted.promise

  const waitingOperation = runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    () => waiting,
    confirmedInjections(locks.managerFor(waiting, waitingRequested.resolve)),
  )
  await waitingRequested.promise
  const rejection = rejectNonOwnerInput()
  const duringWait = await queueSnapshot(queue, scope)
  const ownerDuringWait = locks.owner(lockName)

  releasePrimary.resolve()
  const [, waitingResult] = await Promise.all([
    primaryOperation,
    waitingOperation,
  ])

  return {
    scenarioId: contract.scenarioId,
    observations: [
      observation(point, {
        queue: {
          appendCount: duringWait.count - initial.count,
          unchanged: duringWait.count === initial.count,
        },
        d1: {
          consumed: duringWait.nextD1 !== initial.nextD1,
          next: duringWait.nextD1,
        },
        lock: { owner: ownerDuringWait },
        acceptanceDisplay: {
          shownAsAccepted: rejection.accepted,
          noticeId: rejection.notice.noticeId,
        },
        reinputAvailability: {
          afterLockAcquisition: waitingResult.recordingStarted,
        },
      }),
    ],
  }
}

async function runDurableAppendFailure(
  context: ScenarioContext,
): Promise<FailureScenarioResult> {
  const { contract, queue, scope, initial, locks, options } = context
  const tabs = recordFieldValue(contract.input, 'tabs')
  const [primary, ...extraContexts] = stringArrayProperty(tabs, 'contexts')
  if (!primary || extraContexts.length) {
    throw new Error('シナリオには一つのタブ文脈が必要です')
  }
  const point = singleObservationPoint(contract)
  const lockName = singleWriterLockName(String(scope.game))
  const [uncloneableSlotId] = EVENT_SLOT_IDS
  if (!uncloneableSlotId) {
    throw new Error('故障注入に使うイベントスロットがありません')
  }

  let appendFailure: unknown
  const result = await runAsSingleWriter(
    { gameIdentifier: String(scope.game) },
    async () => {
      try {
        await appendUnderQueueDiscipline(queue, {
          ...appendInput(scope, primary),
          event: {
            fields: { [uncloneableSlotId]: () => undefined },
          },
        })
      } catch (error) {
        appendFailure = error
      }
      if (!appendFailure) {
        throw new Error('永続追記の故障注入が失敗しませんでした')
      }

      if (options.extraPersistence) {
        await appendUnderQueueDiscipline(
          queue,
          appendInput(scope, contract.version),
        )
      }
      const failed = await queueSnapshot(queue, scope)
      const ownerAtFailure = locks.owner(lockName)
      const retry = await appendUnderQueueDiscipline(
        queue,
        appendInput(scope, contract.schemaVersion),
      )

      return observation(point, {
        queue: {
          unchanged: failed.count === initial.count,
          count: failed.count,
          partialAppendCount: Math.max(failed.count - initial.count, [].length),
        },
        d1: {
          consumed: failed.nextD1 !== initial.nextD1,
          next: failed.nextD1,
        },
        lock: { owner: ownerAtFailure },
        acceptanceDisplay: { shownAsAccepted: !appendFailure },
        reinputAvailability: {
          possible: Boolean(appendFailure),
          retryWithSameNextD1: retry.slot.d1 === failed.nextD1,
        },
      })
    },
    confirmedInjections(locks.managerFor(primary)),
  )
  if (!result.recordingStarted) {
    throw new Error('所有文脈が単一書き手として開始されませんでした')
  }

  return {
    scenarioId: contract.scenarioId,
    observations: [result.value],
  }
}

const SCENARIO_RUNNERS = new Map<
  FailureScenarioContract['scenarioId'],
  ScenarioRunner
>([
  [MULTI_TAB_SINGLE_WRITER, runMultiTabSingleWriter],
  [LEADER_FREEZE_REELECTION, runLeaderFreezeReelection],
  [WAITING_INPUT_NOT_ACCEPTED, runWaitingInputNotAccepted],
  [DURABLE_APPEND_FAILURE, runDurableAppendFailure],
])

function deleteDatabase(databaseName: string): Promise<void> {
  return new Promise((resolveDeletion, rejectDeletion) => {
    const request = indexedDB.deleteDatabase(databaseName)
    request.onsuccess = () => resolveDeletion()
    request.onerror = () =>
      rejectDeletion(request.error ?? new Error('テスト DB を削除できません'))
    request.onblocked = () =>
      rejectDeletion(new Error('テスト DB の削除が阻害されました'))
  })
}

async function openScenarioQueue(contract: FailureScenarioContract): Promise<
  Readonly<{
    queue: DurableQueue
    scope: DurableQueueScope
    initial: QueueSnapshot
    databaseName: string
  }>
> {
  const allocation = allocatedDatabaseNames.push(contract.scenarioId)
  const databaseName = `failure-scenario-${contract.scenarioId}-${allocation}`
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => Boolean(contract.schemaVersion),
  })
  const scope = { game: contract.scenarioId, d4: contract.version }
  const initialPersistence = recordFieldValue(
    contract.input,
    'initialPersistence',
  )
  const declaredQueue = recordFieldValue(contract.input, 'queue')
  const declaredD1 = recordFieldValue(contract.input, 'd1')
  const queueCount = numberProperty(initialPersistence, 'queueCount')
  const nextD1 = numberProperty(initialPersistence, 'nextD1')

  if (numberProperty(declaredQueue, 'unsentCount') !== queueCount) {
    throw new Error('初期永続化と未送信キューの件数が一致しません')
  }
  if (numberProperty(declaredD1, 'next') !== nextD1) {
    throw new Error('初期永続化と D1 の次番号が一致しません')
  }

  const markers = Array.from(
    { length: queueCount },
    (_unused, marker) => marker,
  )
  for (const marker of markers) {
    await queue.append(appendInput(scope, marker))
  }
  const initial = await queueSnapshot(queue, scope)
  if (initial.count !== queueCount || initial.nextD1 !== nextD1) {
    throw new Error('資産どおりの初期永続化状態を作れませんでした')
  }

  return { queue, scope, initial, databaseName }
}

/**
 * 版付き故障シナリオ資産をディレクトリから読み、契約検査を通して返す。
 *
 * Returns:
 *   検査済みの故障シナリオ資産。
 */
export function readFailureScenarioAssets(): readonly FailureScenarioContract[] {
  return readdirSync(FAILURE_FIXTURE_DIRECTORY)
    .filter((fileName) => fileName.endsWith('.json'))
    .sort()
    .map((fileName) =>
      parseFailureScenarioContract(
        fileName,
        readFileSync(resolve(FAILURE_FIXTURE_DIRECTORY, fileName), 'utf8'),
      ),
    )
}

/**
 * 資産の入力から製品コードを駆動し、比較契約へ渡す観測結果を返す。
 *
 * Args:
 *   contract: 検査済みの故障シナリオ資産。
 *   options: 変異試験専用の故障注入。
 *
 * Returns:
 *   製品コードの実行から得た観測結果。
 */
export async function executeFailureScenario(
  contract: FailureScenarioContract,
  options: FailureScenarioExecutionOptions = {},
): Promise<FailureScenarioResult> {
  const runner = SCENARIO_RUNNERS.get(contract.scenarioId)
  if (!runner) {
    throw new Error(`シナリオ実行器がありません: ${contract.scenarioId}`)
  }

  const { queue, scope, initial, databaseName } =
    await openScenarioQueue(contract)
  try {
    return await runner({
      contract,
      queue,
      scope,
      initial,
      locks: new MockWebLocks(),
      options,
    })
  } finally {
    queue.close()
    await deleteDatabase(databaseName)
  }
}

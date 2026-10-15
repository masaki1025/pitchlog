import 'fake-indexeddb/auto'

import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import {
  createAckAdapterInjections,
  type D1AckAdapterInput,
} from '../lib/sync/ackAdapter'
import { appendUnderQueueDiscipline } from '../lib/sync/clientDiscipline'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueAppend,
  type DurableQueueScope,
} from '../lib/sync/durableQueue'
import { EVENT_KIND_SLOT_ID, EVENT_SLOT_IDS } from '../lib/sync/eventFieldRules'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import {
  B3_CONTENT_BRANCH,
  B3_REJECTION_KIND,
} from '../lib/sync/rejectionReason'
import { queueStateId, type I6Acceptance } from '../lib/sync/queueState'
import { TARGET_EVENT_REFERENCE_ELEMENTS } from '../lib/sync/syncEvent'
import {
  FAILURE_SCENARIO_IDS,
  parseFailureScenarioContract,
  type FailureScenarioCase,
  type FailureScenarioCaseResult,
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
  persistI6BeforeInjection?: boolean
  skipI6Persistence?: boolean
  skipAckDelivery?: boolean
  i6AcceptedAtOverride?: string
}>

const I6_FIELD_IDS = [
  'i6TargetReference',
  'i6Version',
  'i6D5',
  'i6ConfirmedContent',
  'i6RetentionDeadline',
  'i6EscrowState',
] as const

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
  testCase: FailureScenarioCase
  queue: DurableQueue
  scope: DurableQueueScope
  initial: QueueSnapshot
  locks: MockWebLocks
  options: FailureScenarioExecutionOptions
}>
type ScenarioRunner = (
  context: ScenarioContext,
) => Promise<FailureScenarioCaseResult>

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

function observationPoints(testCase: FailureScenarioCase): readonly string[] {
  return testCase.observations.map(
    (expectedObservation) => expectedObservation.observationPoint,
  )
}

function singleObservationPoint(testCase: FailureScenarioCase): string {
  const [point, ...extra] = observationPoints(testCase)
  if (!point || extra.length) {
    throw new Error('シナリオの観測点は一つでなければなりません')
  }
  return point
}

function pairedObservationPoints(
  testCase: FailureScenarioCase,
): readonly [string, string] {
  const [before, after, ...extra] = observationPoints(testCase)
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

function caseResult(
  testCase: FailureScenarioCase,
  injections: readonly unknown[],
  observations: readonly FailureScenarioObservation[],
): FailureScenarioCaseResult {
  return {
    caseId: testCase.caseId,
    hookCalls: injections.length,
    observations,
  }
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
): Promise<FailureScenarioCaseResult> {
  const { contract, testCase, queue, scope, initial, locks } = context
  const [primary, secondary] = scenarioContexts(contract)
  const point = singleObservationPoint(testCase)
  const injections: unknown[] = []
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
  injections.push(secondary)
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

  return caseResult(testCase, injections, [
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
  ])
}

async function runLeaderFreezeReelection(
  context: ScenarioContext,
): Promise<FailureScenarioCaseResult> {
  const { contract, testCase, queue, scope, initial, locks } = context
  const [primary, waiting] = scenarioContexts(contract)
  const [beforePoint, afterPoint] = pairedObservationPoints(testCase)
  const injections: unknown[] = []
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
  injections.push(primary)

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

  return caseResult(testCase, injections, [
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
  ])
}

async function runWaitingInputNotAccepted(
  context: ScenarioContext,
): Promise<FailureScenarioCaseResult> {
  const { contract, testCase, queue, scope, initial, locks } = context
  const [primary, waiting] = scenarioContexts(contract)
  const point = singleObservationPoint(testCase)
  const injections: unknown[] = []
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
  injections.push(waiting)
  const rejection = rejectNonOwnerInput()
  const duringWait = await queueSnapshot(queue, scope)
  const ownerDuringWait = locks.owner(lockName)

  releasePrimary.resolve()
  const [, waitingResult] = await Promise.all([
    primaryOperation,
    waitingOperation,
  ])

  return caseResult(testCase, injections, [
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
  ])
}

async function runDurableAppendFailure(
  context: ScenarioContext,
): Promise<FailureScenarioCaseResult> {
  const { contract, testCase, queue, scope, initial, locks, options } = context
  const tabs = recordFieldValue(contract.input, 'tabs')
  const [primary, ...extraContexts] = stringArrayProperty(tabs, 'contexts')
  if (!primary || extraContexts.length) {
    throw new Error('シナリオには一つのタブ文脈が必要です')
  }
  const point = singleObservationPoint(testCase)
  const lockName = singleWriterLockName(String(scope.game))
  const injections: unknown[] = []
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
        injections.push(error)
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

  return caseResult(testCase, injections, [result.value])
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

/** このアダプタが実行する scenarioId。 */
export const CLIENT_RUNNER_SCENARIO_IDS: readonly FailureScenarioContract['scenarioId'][] =
  [...SCENARIO_RUNNERS.keys()]

/**
 * サーバー側の runner(`backend/tests/db/test_sync_apply_failure_runner.py`)が
 * 公開入口と DB で実行する scenarioId。このアダプタでは実行しない。
 */
export const SERVER_RUNNER_SCENARIO_IDS = [
  'tombstone-application',
  'revision-application',
  'p1-crash-boundaries',
  'p2-crash-boundaries',
  'p3-crash-boundaries',
  'p4-crash-boundaries',
  'p5-b3a-crash-boundaries',
  'p5-b3b-unreached-t9',
  'd1-mixed-batch',
  'b3b-after-gap',
  'p3-invalidation-consumed-before-complete',
  'o4-persisted-d2-equivalence',
] as const satisfies readonly FailureScenarioContract['scenarioId'][]

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
    await queue.append(queue.prepareAppend(appendInput(scope, marker)))
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
  const [testCase, ...extraCases] = contract.cases
  if (!testCase || extraCases.length) {
    throw new Error('クライアント側シナリオの case は一つでなければなりません')
  }

  const { queue, scope, initial, databaseName } =
    await openScenarioQueue(contract)
  try {
    const executed = await runner({
      contract,
      testCase,
      queue,
      scope,
      initial,
      locks: new MockWebLocks(),
      options,
    })
    return { scenarioId: contract.scenarioId, cases: [executed] }
  } finally {
    queue.close()
    await deleteDatabase(databaseName)
  }
}

/**
 * サーバー側の資産のうち、端末の状態をこのアダプタが観測する case とフィールド。
 *
 * サーバー側の runner(`backend/tests/db/test_sync_apply_failure_runner.py` の
 * `CLIENT_OBSERVED_FIELDS`)は同じ case の残りのフィールドを観測する。
 */
export const CLIENT_OBSERVED_CASES = [
  {
    scenarioId: 'p3-crash-boundaries',
    caseId: 'server-confirmed-before-i6',
    fieldIds: I6_FIELD_IDS,
  },
  {
    scenarioId: 'p3-crash-boundaries',
    caseId: 'i6-persisted-then-closed',
    fieldIds: I6_FIELD_IDS,
  },
] as const satisfies readonly Readonly<{
  scenarioId: FailureScenarioContract['scenarioId']
  caseId: string
  fieldIds: readonly string[]
}>[]

function sameJson(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

type I6Expectation = Readonly<{
  acceptance: I6Acceptance
  acceptedAt: string
}>

function readVerifiedI6Response(
  contract: FailureScenarioContract,
): I6Expectation {
  // 同じ共有応答をサーバー runner が実際の応答・台帳と照合する。
  const response = requireRecord(
    JSON.parse(
      readFileSync(
        resolve(
          cwd(),
          '../tests/fixtures/sync-protocol-i6-server-response_v1.json',
        ),
        'utf8',
      ),
    ),
    'I6 サーバー応答',
  )
  if (response.scenarioId !== contract.scenarioId) {
    throw new Error('I6 サーバー応答のシナリオが一致しません')
  }
  const queueInput = recordFieldValue(contract.input, 'queue')
  const changes = queueInput.unsent
  if (!Array.isArray(changes) || changes.length !== [contract].length) {
    throw new Error('I6 の変更イベントが一件ではありません')
  }
  const [firstChange] = changes
  const change = requireRecord(firstChange, 'queue.unsent[0]')
  const target = requireRecord(change.target, 'queue.unsent[0].target')
  const reference = requireRecord(
    response.targetReference,
    'I6.targetReference',
  )
  const [targetGame, targetD4, targetD1] = TARGET_EVENT_REFERENCE_ELEMENTS
  if (
    !targetGame ||
    !targetD4 ||
    !targetD1 ||
    typeof reference[targetGame] !== 'string' ||
    reference[targetD4] !== recordFieldValue(contract.input, 'd4').request ||
    reference[targetD1] !== target.d1 ||
    response.expectedVersion !== change.expectedVersion ||
    response.d5 !== change.d5 ||
    !sameJson(response.confirmedContent, change.payload) ||
    typeof response.acceptedAt !== 'string'
  ) {
    throw new Error('I6 サーバー応答が要求の変更イベントと一致しません')
  }
  return {
    acceptance: {
      targetReference: reference as I6Acceptance['targetReference'],
      expectedVersion: response.expectedVersion,
      d5: response.d5,
      confirmedContent: response.confirmedContent,
    },
    acceptedAt: response.acceptedAt,
  }
}

async function observeI6(
  databaseName: string,
  observationPoint: string,
  { acceptance, acceptedAt }: I6Expectation,
): Promise<FailureScenarioObservation> {
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => Boolean(databaseName),
  })
  try {
    const slot = await queue.readI6(acceptance.d5)
    const evacuation = await queue.prepareI6Evacuation(acceptance.d5, {
      confirmI6EvacuationSaved: () => Boolean(slot),
    })
    let keptOnReplay: boolean | null = null
    if (slot) {
      // 保存済み結果の再掲(別の accepted_at)で accepted_at の起点を動かさないこと。
      const replay = queue.prepareI6Acceptance(acceptance, {
        resolveAcceptedAt: () => ({
          known: Boolean(slot),
          targetReference: acceptance.targetReference,
          acceptedAt: `${acceptedAt}-replayed`,
        }),
      })
      if (replay) {
        await queue.persistI6Acceptance(replay)
      }
      const after = await queue.readI6(acceptance.d5)
      keptOnReplay = after?.acceptedAt === acceptedAt
    }
    const matches = (stored: unknown, accepted: unknown) =>
      slot ? sameJson(stored, accepted) : null
    return observation(observationPoint, {
      i6TargetReference: {
        persisted: Boolean(slot),
        matchesAcceptance: matches(
          slot?.targetReference,
          acceptance.targetReference,
        ),
      },
      i6Version: {
        persisted: Boolean(slot),
        matchesAcceptance: matches(
          slot?.expectedVersion,
          acceptance.expectedVersion,
        ),
      },
      i6D5: {
        persisted: Boolean(slot),
        matchesAcceptance: matches(slot?.d5, acceptance.d5),
      },
      i6ConfirmedContent: {
        persisted: Boolean(slot),
        matchesAcceptance: matches(
          slot?.confirmedContent,
          acceptance.confirmedContent,
        ),
      },
      i6RetentionDeadline: {
        fromServerAcceptedAt: slot ? slot.acceptedAt === acceptedAt : null,
        keptOnReplay,
      },
      i6EscrowState: {
        evacuated: slot?.state === queueStateId('退避済み'),
        collectible: Boolean(evacuation),
      },
    })
  } finally {
    queue.close()
  }
}

/**
 * P3 の受理結果をサーバーの確定応答(accepted_at)まで受けた後にブラウザが終了する
 * 注入を、製品の永続キューで起こす。トランザクション外の注入点(サーバー確定後・
 * I6 端末永続化前)では永続化の前に、クライアント操作の注入(I6 の端末永続化)では
 * 永続化の確定後に終了する。
 */
async function runI6BrowserClose(
  contract: FailureScenarioContract,
  testCase: FailureScenarioCase,
  options: FailureScenarioExecutionOptions,
): Promise<FailureScenarioCaseResult> {
  const expectation = readVerifiedI6Response(contract)
  const injectionTarget = requireRecord(
    fieldValue(testCase.faultInjection, 'target'),
    'faultInjection.target',
  )
  const persistsBeforeClose =
    injectionTarget.kind === 'client'
      ? !options.skipI6Persistence
      : Boolean(options.persistI6BeforeInjection)
  const [injectionPoint, restartPoint, ...extra] = observationPoints(testCase)
  if (!injectionPoint || !restartPoint || extra.length) {
    throw new Error('I6 の注入には二つの観測点が必要です')
  }

  const allocation = allocatedDatabaseNames.push(contract.scenarioId)
  const databaseName = `failure-scenario-i6-${contract.scenarioId}-${allocation}`
  const injections: unknown[] = []
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => Boolean(contract.schemaVersion),
  })
  try {
    // サーバーの確定応答を受け、I6 の永続化を準備した時点。
    const preparation = queue.prepareI6Acceptance(expectation.acceptance, {
      resolveAcceptedAt: () => ({
        known: Boolean(expectation.acceptance.targetReference),
        targetReference: expectation.acceptance.targetReference,
        acceptedAt: options.i6AcceptedAtOverride ?? expectation.acceptedAt,
      }),
    })
    if (!preparation) {
      throw new Error('I6 の永続化を準備できませんでした')
    }
    if (persistsBeforeClose) {
      await queue.persistI6Acceptance(preparation)
    }
    // ブラウザが終了する。
    injections.push(preparation)
  } finally {
    queue.close()
  }
  try {
    return caseResult(testCase, injections, [
      await observeI6(databaseName, injectionPoint, expectation),
      await observeI6(databaseName, restartPoint, expectation),
    ])
  } finally {
    await deleteDatabase(databaseName)
  }
}

/**
 * サーバー側の資産の case のうち、端末の状態だけをこのアダプタで観測する。
 *
 * Args:
 *   contract: 検査済みの故障シナリオ資産。
 *   caseId: `CLIENT_OBSERVED_CASES` の case。
 *   options: 変異試験専用の故障注入。
 *
 * Returns:
 *   担当フィールドだけを持つ、その case の観測結果。
 */
/** 端末のキューを観測する適用経路(D1 付きのイベントを端末のキューに積む経路)。 */
const QUEUE_OBSERVED_PATHS: readonly unknown[] = ['P1', 'P2', 'P4', 'P5']

/**
 * サーバー側の資産の case のうち、このアダプタが観測するフィールドを返す。
 *
 * I6 の case は I6 の 6 フィールドを、D1 付き経路の case は端末のキューを観測する。
 * サーバー側の runner は同じ規則で残りのフィールドを観測する。
 *
 * Args:
 *   contract: 検査済みの故障シナリオ資産。
 *   caseId: case の ID。
 *
 * Returns:
 *   このアダプタが観測するフィールド(観測しなければ空)。
 */
export function clientObservedFieldIds(
  contract: FailureScenarioContract,
  caseId: string,
): readonly string[] {
  const i6 = CLIENT_OBSERVED_CASES.find(
    (candidate) =>
      candidate.scenarioId === contract.scenarioId &&
      candidate.caseId === caseId,
  )
  if (i6) {
    return i6.fieldIds
  }
  const path = contract.input.applicationPath
  if (
    path &&
    Object.hasOwn(path, 'value') &&
    QUEUE_OBSERVED_PATHS.includes(fieldValue(contract.input, 'applicationPath'))
  ) {
    return ['queue', 'lock', 'acceptanceDisplay', 'reinputAvailability']
  }
  return []
}

type QueueEventSpec = Readonly<{
  d5: string
  d1: number
  kind: string
  registration?: string
  tombstoneOf?: string
  revisionOf?: string
}>

function eventKindName(spec: QueueEventSpec): string {
  if (spec.registration) {
    return '選手のその場登録'
  }
  if (spec.tombstoneOf) {
    return '墓標'
  }
  return spec.revisionOf ? '改訂版' : '毎球入力'
}

function queueEventOf(spec: QueueEventSpec): DurableQueueAppend['event'] {
  const kind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === eventKindName(spec),
  )
  if (!kind) {
    throw new Error(`イベント種別がありません: ${spec.kind}`)
  }
  return { fields: { [EVENT_KIND_SLOT_ID]: kind.id } }
}

function requestEvents(contract: FailureScenarioContract): QueueEventSpec[] {
  const queueInput = recordFieldValue(contract.input, 'queue')
  const byD1 = new Map<number, QueueEventSpec>()
  for (const list of [queueInput.unsent, queueInput.restartUnsent]) {
    for (const candidate of Array.isArray(list) ? list : []) {
      const spec = requireRecord(candidate, 'queue.unsent') as QueueEventSpec
      byD1.set(spec.d1, spec)
    }
  }
  return [...byD1.values()].sort((left, right) => left.d1 - right.d1)
}

/**
 * サーバー側の runner で確かめた ACK を、端末が受け取ったものとして製品の ACK
 * アダプタとキュー遷移へ通し、端末のキューの状態を観測する。
 *
 * ACK 消失の注入では、最初の観測点の ACK を端末へ届けない。
 */
async function runQueueObservation(
  contract: FailureScenarioContract,
  testCase: FailureScenarioCase,
  options: FailureScenarioExecutionOptions,
): Promise<FailureScenarioCaseResult> {
  const events = requestEvents(contract)
  const scope = {
    game: contract.scenarioId,
    d4: recordFieldValue(contract.input, 'd4').request,
  }
  const allocation = allocatedDatabaseNames.push(contract.scenarioId)
  const databaseName = `failure-scenario-queue-${contract.scenarioId}-${allocation}`
  const queue = await openDurableQueue({
    databaseName,
    requestStoragePersistence: async () => Boolean(contract.schemaVersion),
  })
  const [primary] = scenarioContexts(contract)
  const locks = new MockWebLocks()
  const lockName = singleWriterLockName(String(scope.game))
  const injectionTarget = requireRecord(
    fieldValue(testCase.faultInjection, 'target'),
    'faultInjection.target',
  )
  // 注入そのものはサーバー側 runner が実行して呼び出し回数を観測する。ここでは
  // 資産の到達性に合わせて数える(端末側の独立な証拠ではない — worklog)。
  const reachability = fieldValue(
    testCase.faultInjection,
    'expectedReachability',
  )
  const injections: unknown[] =
    reachability === 'unreached' ? [] : [injectionTarget]
  try {
    const [first] = events
    if (!first) {
      throw new Error('端末のキューに積むイベントがありません')
    }
    // 要求より前の D1 は、この試験の観測対象でない既存のキュー行として積む。
    while ((await queue.readNextD1(scope)) < first.d1) {
      await queue.append(
        queue.prepareAppend(appendInput(scope, await queue.readNextD1(scope))),
      )
    }
    for (const spec of events) {
      while ((await queue.readNextD1(scope)) < spec.d1) {
        await queue.append(
          queue.prepareAppend(
            appendInput(scope, await queue.readNextD1(scope)),
          ),
        )
      }
      const slot = await queue.append(
        queue.prepareAppend({
          scope,
          d5: spec.d5,
          version: spec.d5,
          event: queueEventOf(spec),
        }),
      )
      if (slot.d1 !== spec.d1) {
        throw new Error('端末のキューの D1 が資産と一致しません')
      }
    }

    const results: FailureScenarioObservation[] = []
    for (const [index, assetObservation] of testCase.observations.entries()) {
      const observed = await runAsSingleWriter(
        { gameIdentifier: String(scope.game) },
        async () => {
          const ackLost =
            injectionTarget.kind === 'client' &&
            injectionTarget.operation === 'ACK の受信' &&
            !index
          const d1Field = requireRecord(assetObservation.fields.d1, 'fields.d1')
          if (
            !ackLost &&
            !options.skipAckDelivery &&
            Array.isArray(d1Field.ack)
          ) {
            await deliverAck(queue, scope, events, assetObservation, d1Field)
          }
          const states: [number, string | null, string | null][] = []
          for (const spec of events) {
            const slot = await queue.readSlot(scope, spec.d1)
            states.push([
              spec.d1,
              slot?.state ?? null,
              slot?.actionRequiredLabel ?? null,
            ])
          }
          return {
            queue: { states },
            lock: { owner: locks.owner(lockName) },
            acceptanceDisplay: {
              serverAcceptedD1s: states
                .filter(([, state]) => state === '同期済み')
                .map(([d1]) => d1),
            },
            reinputAvailability: {
              reinputRequired: states.some(([, state]) => state === null),
              automaticResendD1s: states
                .filter(([, state]) => state === '未送信')
                .map(([d1]) => d1),
              correctionRequiredD1s: states
                .filter(([, state]) => state === '要操作')
                .map(([d1]) => d1),
            },
          }
        },
        confirmedInjections(locks.managerFor(primary)),
      )
      if (!observed.recordingStarted) {
        throw new Error('単一書き手のロックを取得できません')
      }
      results.push(
        observation(assetObservation.observationPoint, observed.value),
      )
    }
    return caseResult(testCase, injections, results)
  } finally {
    queue.close()
    await deleteDatabase(databaseName)
  }
}

async function deliverAck(
  queue: DurableQueue,
  scope: DurableQueueScope,
  events: readonly QueueEventSpec[],
  assetObservation: FailureScenarioObservation,
  d1Field: Record<string, unknown>,
): Promise<void> {
  const idempotent = requireRecord(
    assetObservation.fields.idempotentResult,
    'fields.idempotentResult',
  )
  const ack = d1Field.ack as readonly (readonly [number, string])[]
  const specByD1 = new Map(events.map((spec) => [spec.d1, spec]))
  const mapping = assetObservation.fields.temporaryIdMapping
  const acknowledged =
    mapping && typeof mapping === 'object' && 'acknowledged' in mapping
      ? (mapping.acknowledged as string[])
      : []
  const registration = events.find((spec) => spec.registration)
  const boundary = idempotent.boundary
  const branch = idempotent.b3Branch
  const reasonEvidence = idempotent.responseReason
  const reason =
    reasonEvidence &&
    typeof reasonEvidence === 'object' &&
    'present' in reasonEvidence &&
    reasonEvidence.present
      ? 'サーバー応答に理由あり'
      : undefined
  const injections = createAckAdapterInjections({
    d1: {
      envelope: {
        advancedD3: d1Field.ackD3,
        eventResults: ack.map(([d1, a5Result]) => ({
          d4: scope.d4,
          d1,
          d5: specByD1.get(d1)?.d5,
          a5Result,
        })),
        ...(acknowledged.length
          ? {
              playerIdMappings: acknowledged.map((temporaryId) => ({
                temporaryId,
                officialId: `${temporaryId}-official`,
              })),
            }
          : {}),
      },
      boundaryResult: boundary,
      ...(branch
        ? {
            b3Rejection:
              branch === B3_REJECTION_KIND.O4
                ? {
                    kind: B3_REJECTION_KIND.O4,
                    reason,
                  }
                : {
                    kind: B3_REJECTION_KIND.CONTENT,
                    branch:
                      branch === B3_CONTENT_BRANCH.B3A
                        ? B3_CONTENT_BRANCH.B3A
                        : B3_CONTENT_BRANCH.B3B,
                    reason,
                  },
          }
        : {}),
      ...(registration?.registration && acknowledged.length
        ? {
            playerIdMappingTarget: {
              eventKind: EVENT_KIND_RULES.find(
                (candidate) => candidate.name === eventKindName(registration),
              ),
              event: queueEventOf(registration),
              key: {
                d4: scope.d4,
                d1: registration.d1,
                d5: registration.d5,
              },
              temporaryId: registration.registration,
            },
          }
        : {}),
    } as D1AckAdapterInput,
  })
  for (const [d1] of ack) {
    const preparation = await queue.prepareA5Transition(scope, d1, injections)
    if (preparation) {
      await queue.persistA5Transition(preparation)
    }
  }
}

export async function executeClientObservedCase(
  contract: FailureScenarioContract,
  caseId: string,
  options: FailureScenarioExecutionOptions = {},
): Promise<FailureScenarioResult> {
  const fieldIds = clientObservedFieldIds(contract, caseId)
  const testCase = contract.cases.find(
    (candidate) => candidate.caseId === caseId,
  )
  if (!fieldIds.length || !testCase) {
    throw new Error(`端末を観測する case がありません: ${caseId}`)
  }
  const isI6 = CLIENT_OBSERVED_CASES.some(
    (candidate) =>
      candidate.scenarioId === contract.scenarioId &&
      candidate.caseId === caseId,
  )
  return {
    scenarioId: contract.scenarioId,
    cases: [
      isI6
        ? await runI6BrowserClose(contract, testCase, options)
        : await runQueueObservation(contract, testCase, options),
    ],
  }
}

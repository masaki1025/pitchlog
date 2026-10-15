export const FAILURE_SCENARIO_IDS = [
  'multi-tab-single-writer',
  'leader-freeze-reelection',
  'waiting-input-not-accepted',
  'durable-append-failure',
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
] as const

export type FailureScenarioId = (typeof FAILURE_SCENARIO_IDS)[number]

/**
 * 資産の構造の版(正本 SP 10-3 v0.8 の case 構造)。
 *
 * 経路と T 要素の対応・T の内部単位・P5 の値関係・母集合と注入被覆の照合は
 * サーバー側の契約検査(`backend/tests/test_sync_apply_failure_contract.py`)が正で、
 * ここでは消費側として構造を fail-closed に検査する。
 */
export const FAILURE_SCENARIO_SCHEMA_VERSION = 2

/** 全観測点が無条件に持つ共通の期待フィールド(SP 10-3「共通の期待フィールド」)。 */
export const FAILURE_EXPECTED_FIELD_IDS = [
  'queue',
  'd1',
  'lock',
  'acceptanceDisplay',
  'reinputAvailability',
  'prefix',
  'idempotentResult',
  'temporaryIdMapping',
  'recordingRight',
  'tElementCommitment',
] as const

export type FailureExpectedFieldId = (typeof FAILURE_EXPECTED_FIELD_IDS)[number]

/** 適用経路を持たないクライアント側の資産で省略できない 10-2 の期待値。 */
export const CLIENT_REQUIRED_FIELD_IDS = [
  'queue',
  'd1',
  'lock',
  'acceptanceDisplay',
  'reinputAvailability',
] as const satisfies readonly FailureExpectedFieldId[]

/** D1 付きのサーバー経路も端末の ACK 経路で観測する期待値。 */
const D1_CLIENT_REQUIRED_FIELD_IDS = [
  'lock',
  'acceptanceDisplay',
  'reinputAvailability',
] as const satisfies readonly FailureExpectedFieldId[]

export type FailureScenarioField =
  Readonly<{ value: unknown }> | Readonly<{ omittedBecause: string }>

export type FailureInjectionTarget =
  | Readonly<{ kind: 'transaction'; path: string; tElement: string }>
  | Readonly<{ kind: 'outOfTransaction'; point: string }>
  | Readonly<{ kind: 'client'; operation: string }>

export type FailureScenarioObservation = Readonly<{
  observationPoint: string
  fields: Readonly<Record<string, unknown>>
}>

export type FailureScenarioCase = Readonly<{
  caseId: string
  faultInjection: Readonly<Record<string, FailureScenarioField>>
  observations: readonly FailureScenarioObservation[]
}>

export type FailureScenarioComparisonUnit = Readonly<{
  scenarioId: FailureScenarioId
  caseId: string
  injectionTarget: string
  observationPoint: string
  expectedField: string
}>

export type FailureScenarioContract = Readonly<{
  schemaVersion: typeof FAILURE_SCENARIO_SCHEMA_VERSION
  scenarioId: FailureScenarioId
  version: number
  input: Readonly<Record<string, FailureScenarioField>>
  cases: readonly FailureScenarioCase[]
  comparisonUnit: readonly FailureScenarioComparisonUnit[]
}>

export type FailureScenarioCaseResult = Readonly<{
  caseId: string
  hookCalls: number
  observations: readonly FailureScenarioObservation[]
}>

export type FailureScenarioResult = Readonly<{
  scenarioId: FailureScenarioId
  cases: readonly FailureScenarioCaseResult[]
}>

const ROOT_FIELD_IDS = [
  'schemaVersion',
  'scenarioId',
  'version',
  'input',
  'cases',
  'comparisonUnit',
] as const

const INPUT_FIELD_IDS = [
  'initialPersistence',
  'queue',
  'd1',
  'd3',
  'd4',
  'd5',
  'currentRecoveryGeneration',
  'requestRecoveryGeneration',
  'applicationPath',
  'tabs',
  'lock',
  'p5Branch',
] as const

const CASE_FIELD_IDS = ['caseId', 'faultInjection', 'observations'] as const
const FAULT_INJECTION_FIELD_IDS = [
  'target',
  'injectionPoint',
  'stopOperation',
  'restartOperation',
  'expectedReachability',
] as const
const OBSERVATION_FIELD_IDS = ['observationPoint', 'fields'] as const
const COMPARISON_UNIT_FIELD_IDS = [
  'scenarioId',
  'caseId',
  'injectionTarget',
  'observationPoint',
  'expectedField',
] as const
const RESULT_FIELD_IDS = ['scenarioId', 'cases'] as const
const RESULT_CASE_FIELD_IDS = ['caseId', 'hookCalls', 'observations'] as const
const APPLICATION_PATHS = ['P1', 'P2', 'P3', 'P4', 'P5'] as const
const REACHABILITIES = ['reached', 'unreached'] as const
const FILE_NAME_PATTERN = /^([a-z0-9]+(?:-[a-z0-9]+)*)_v([1-9]\d*)\.json$/
const CASE_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

export class FailureScenarioContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FailureScenarioContractError'
  }
}

function fail(message: string): never {
  throw new FailureScenarioContractError(message)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function requireExactKeys(
  value: unknown,
  expectedKeys: readonly string[],
  location: string,
): Record<string, unknown> {
  if (!isRecord(value)) {
    return fail(`${location} はオブジェクトでなければなりません`)
  }

  const actualKeys = Object.keys(value)
  if (
    actualKeys.length !== expectedKeys.length ||
    actualKeys.some((key, index) => key !== expectedKeys[index])
  ) {
    return fail(
      `${location} のキーまたは順序が一致しません: ${actualKeys.join(',')}`,
    )
  }
  return value
}

function requireNonEmptyString(value: unknown, location: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return fail(`${location} は空でない文字列でなければなりません`)
  }
  return value
}

function requireNonEmptyArray(value: unknown, location: string): unknown[] {
  if (!Array.isArray(value) || value.length === 0) {
    return fail(`${location} は空でない配列でなければなりません`)
  }
  return value
}

function requireScenarioId(
  value: unknown,
  location: string,
): FailureScenarioId {
  if (
    typeof value !== 'string' ||
    !FAILURE_SCENARIO_IDS.some((scenarioId) => scenarioId === value)
  ) {
    return fail(`${location} は既知の scenarioId でなければなりません`)
  }
  return value as FailureScenarioId
}

function isOmitted(value: unknown): boolean {
  return (
    isRecord(value) &&
    Object.keys(value).length === 1 &&
    Object.hasOwn(value, 'omittedBecause')
  )
}

/** `{value}` なら値を、`{omittedBecause}` なら undefined を返す。 */
function validateField(value: unknown, location: string): unknown {
  if (!isRecord(value)) {
    fail(`${location} は値または省略理由を持たなければなりません`)
  }

  const keys = Object.keys(value)
  if (keys.length !== 1) {
    fail(`${location} は値または省略理由の一方だけを持たなければなりません`)
  }
  if (keys[0] === 'value') {
    if (value.value === undefined || value.value === null) {
      fail(`${location} の値を暗黙に省略できません`)
    }
    return value.value
  }
  if (keys[0] === 'omittedBecause') {
    requireNonEmptyString(value.omittedBecause, `${location}.omittedBecause`)
    return undefined
  }
  return fail(`${location} に未知のフィールドがあります`)
}

function validateFieldSection(
  value: unknown,
  fieldIds: readonly string[],
  location: string,
): Record<string, unknown> {
  const section = requireExactKeys(value, fieldIds, location)
  for (const fieldId of fieldIds) {
    validateField(section[fieldId], `${location}.${fieldId}`)
  }
  return section
}

function requiredFieldValue(
  section: Record<string, unknown>,
  fieldId: string,
  location: string,
): unknown {
  const value = validateField(section[fieldId], `${location}.${fieldId}`)
  if (value === undefined) {
    fail(`${location}.${fieldId} は省略できません`)
  }
  return value
}

/**
 * 比較単位に載せる注入対象の正規表記を返す。
 *
 * Args:
 *   target: 検査済みの注入対象。
 *
 * Returns:
 *   `P1:T2`・`P3:<注入点>`・`client:<操作>` のいずれか。
 */
export function injectionTargetKey(target: FailureInjectionTarget): string {
  switch (target.kind) {
    case 'transaction':
      return `${target.path}:${target.tElement}`
    case 'outOfTransaction':
      return `P3:${target.point}`
    case 'client':
      return `client:${target.operation}`
  }
}

function validateTarget(
  value: unknown,
  applicationPath: string | undefined,
  location: string,
): FailureInjectionTarget {
  if (!isRecord(value)) {
    return fail(`${location} はオブジェクトでなければなりません`)
  }
  if (value.kind === 'transaction') {
    requireExactKeys(value, ['kind', 'path', 'tElement'], location)
    if (value.path !== applicationPath) {
      fail(`${location} の注入経路が applicationPath と一致しません`)
    }
    requireNonEmptyString(value.tElement, `${location}.tElement`)
  } else if (value.kind === 'outOfTransaction') {
    requireExactKeys(value, ['kind', 'point'], location)
    if (applicationPath !== 'P3') {
      fail(`${location} のトランザクション外注入は P3 だけです`)
    }
    requireNonEmptyString(value.point, `${location}.point`)
  } else if (value.kind === 'client') {
    requireExactKeys(value, ['kind', 'operation'], location)
    requireNonEmptyString(value.operation, `${location}.operation`)
  } else {
    fail(`${location}.kind が未知です`)
  }
  return value as FailureInjectionTarget
}

function validateExpectedFields(
  value: unknown,
  applicationPath: string | undefined,
  location: string,
): readonly string[] {
  if (!isRecord(value)) {
    return fail(`${location} はオブジェクトでなければなりません`)
  }
  const keys = Object.keys(value)
  const common = keys.slice(0, FAILURE_EXPECTED_FIELD_IDS.length)
  if (
    common.length !== FAILURE_EXPECTED_FIELD_IDS.length ||
    common.some((key, index) => key !== FAILURE_EXPECTED_FIELD_IDS[index])
  ) {
    fail(`${location} は共通の期待フィールドを順に持たなければなりません`)
  }
  if (
    applicationPath === undefined &&
    keys.length !== FAILURE_EXPECTED_FIELD_IDS.length
  ) {
    fail(`${location} に未知の期待フィールドがあります`)
  }
  for (const fieldId of keys) {
    const field = value[fieldId]
    if (field === undefined || field === null) {
      fail(`${location}.${fieldId} を省略できません`)
    }
    if (isOmitted(field)) {
      requireNonEmptyString(
        (field as Record<string, unknown>).omittedBecause,
        `${location}.${fieldId}.omittedBecause`,
      )
      if (
        (applicationPath === undefined &&
          CLIENT_REQUIRED_FIELD_IDS.some((required) => required === fieldId)) ||
        (['P1', 'P2', 'P4', 'P5'].includes(applicationPath ?? '') &&
          D1_CLIENT_REQUIRED_FIELD_IDS.some((required) => required === fieldId))
      ) {
        fail(`${location}.${fieldId} に省略理由は指定できません`)
      }
    } else if (isRecord(field) && Object.hasOwn(field, 'omittedBecause')) {
      fail(`${location}.${fieldId} の省略表現が不正です`)
    }
  }
  const idempotent = value.idempotentResult
  if (
    isRecord(idempotent) &&
    idempotent.b3Branch === 'B3b' &&
    (idempotent.responseReason === undefined ||
      idempotent.responseReason === null)
  ) {
    fail(`${location}.idempotentResult.B3b の応答には理由が必要です`)
  }
  if (
    isRecord(idempotent) &&
    idempotent.responseReason !== undefined &&
    idempotent.responseReason !== null
  ) {
    const reason = idempotent.responseReason
    if (
      !isRecord(reason) ||
      reason.present !== true ||
      !Object.hasOwn(reason, 'matchesSaved') ||
      (reason.matchesSaved !== null && reason.matchesSaved !== true)
    ) {
      fail(
        `${location}.idempotentResult.responseReason は理由の有無と保存済み理由の一致を表します`,
      )
    }
  }
  return keys
}

type ExpectedUnit = Readonly<{
  caseId: string
  injectionTarget: string
  observationPoint: string
  expectedField: string
}>

function validateCases(
  value: unknown,
  applicationPath: string | undefined,
): ExpectedUnit[] {
  const cases = requireNonEmptyArray(value, 'cases')
  const seenCaseIds = new Set<string>()
  const seenInjections = new Set<string>()
  const units: ExpectedUnit[] = []

  cases.forEach((candidate, caseIndex) => {
    const location = `cases[${caseIndex}]`
    const testCase = requireExactKeys(candidate, CASE_FIELD_IDS, location)
    const caseId = requireNonEmptyString(testCase.caseId, `${location}.caseId`)
    if (!CASE_ID_PATTERN.test(caseId)) {
      fail(`${location}.caseId は小文字英数とハイフンでなければなりません`)
    }
    if (seenCaseIds.has(caseId)) {
      fail(`caseId が重複しています: ${caseId}`)
    }
    seenCaseIds.add(caseId)

    const injectionLocation = `${location}.faultInjection`
    const injection = validateFieldSection(
      testCase.faultInjection,
      FAULT_INJECTION_FIELD_IDS,
      injectionLocation,
    )
    const target = validateTarget(
      requiredFieldValue(injection, 'target', injectionLocation),
      applicationPath,
      `${injectionLocation}.target.value`,
    )
    const point = requireNonEmptyString(
      requiredFieldValue(injection, 'injectionPoint', injectionLocation),
      `${injectionLocation}.injectionPoint.value`,
    )
    const reachability = requiredFieldValue(
      injection,
      'expectedReachability',
      injectionLocation,
    )
    if (!REACHABILITIES.some((candidate) => candidate === reachability)) {
      fail(`${injectionLocation}.expectedReachability が未知です`)
    }
    const injectionTarget = injectionTargetKey(target)
    const injectionKey = JSON.stringify([injectionTarget, point])
    if (seenInjections.has(injectionKey)) {
      fail(`同じ注入が重複しています: ${injectionTarget}`)
    }
    seenInjections.add(injectionKey)

    const observations = requireNonEmptyArray(
      testCase.observations,
      `${location}.observations`,
    )
    const seenPoints = new Set<string>()
    observations.forEach((rawObservation, observationIndex) => {
      const observationLocation = `${location}.observations[${observationIndex}]`
      const observation = requireExactKeys(
        rawObservation,
        OBSERVATION_FIELD_IDS,
        observationLocation,
      )
      const observationPoint = requireNonEmptyString(
        observation.observationPoint,
        `${observationLocation}.observationPoint`,
      )
      if (seenPoints.has(observationPoint)) {
        fail(`観測点が重複しています: ${observationPoint}`)
      }
      seenPoints.add(observationPoint)
      const fieldIds = validateExpectedFields(
        observation.fields,
        applicationPath,
        `${observationLocation}.fields`,
      )
      for (const expectedField of fieldIds) {
        units.push({
          caseId,
          injectionTarget,
          observationPoint,
          expectedField,
        })
      }
    })
  })
  return units
}

function validateComparisonUnits(
  value: unknown,
  scenarioId: FailureScenarioId,
  expectedUnits: readonly ExpectedUnit[],
): void {
  if (!Array.isArray(value)) {
    fail('comparisonUnit は配列でなければなりません')
  }
  if (value.length !== expectedUnits.length) {
    fail(
      'comparisonUnit は全 case・全観測点・全期待フィールドを含まなければなりません',
    )
  }

  value.forEach((candidate, index) => {
    const unit = requireExactKeys(
      candidate,
      COMPARISON_UNIT_FIELD_IDS,
      `comparisonUnit[${index}]`,
    )
    const expected = expectedUnits[index]
    if (
      !expected ||
      unit.scenarioId !== scenarioId ||
      unit.caseId !== expected.caseId ||
      unit.injectionTarget !== expected.injectionTarget ||
      unit.observationPoint !== expected.observationPoint ||
      unit.expectedField !== expected.expectedField
    ) {
      fail(`comparisonUnit[${index}] の内容または順序が一致しません`)
    }
  })
}

function structurallyEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right)) {
      return false
    }
    return (
      left.length === right.length &&
      left.every((item, index) => structurallyEqual(item, right[index]))
    )
  }
  if (!isRecord(left) || !isRecord(right)) {
    return false
  }
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key, index) =>
        key === rightKeys[index] && structurallyEqual(left[key], right[key]),
    )
  )
}

/**
 * 版付きファイルの JSON テキストを検査して資産契約として返す。
 *
 * Args:
 *   fileName: 版を含むファイル名。
 *   source: JSON テキスト。
 *
 * Returns:
 *   検査済みの故障シナリオ資産契約。
 *
 * Raises:
 *   FailureScenarioContractError: JSON または資産契約が不正な場合。
 */
export function parseFailureScenarioContract(
  fileName: string,
  source: string,
): FailureScenarioContract {
  let parsed: unknown
  try {
    parsed = JSON.parse(source)
  } catch {
    return fail(`${fileName} は有効な JSON ではありません`)
  }
  return validateFailureScenarioContract(fileName, parsed)
}

/**
 * ファイル名・入力・case・比較単位を fail-closed で検査する。
 *
 * Args:
 *   fileName: 版を含むファイル名。
 *   value: JSON から読み込んだ値。
 *
 * Returns:
 *   検査済みの故障シナリオ資産契約。
 *
 * Raises:
 *   FailureScenarioContractError: 未知・欠落・順序違い・重複を含む場合。
 */
export function validateFailureScenarioContract(
  fileName: string,
  value: unknown,
): FailureScenarioContract {
  const fileNameMatch = FILE_NAME_PATTERN.exec(fileName)
  if (!fileNameMatch) {
    return fail(`ファイル名が版付け規則に一致しません: ${fileName}`)
  }

  const root = requireExactKeys(value, ROOT_FIELD_IDS, fileName)
  if (root.schemaVersion !== FAILURE_SCENARIO_SCHEMA_VERSION) {
    fail(
      `schemaVersion は ${FAILURE_SCENARIO_SCHEMA_VERSION} でなければなりません`,
    )
  }
  const scenarioId = requireScenarioId(root.scenarioId, 'scenarioId')
  const version = root.version
  if (
    typeof version !== 'number' ||
    !Number.isInteger(version) ||
    version <= 0
  ) {
    return fail('version は正の整数でなければなりません')
  }
  if (fileNameMatch[1] !== scenarioId || Number(fileNameMatch[2]) !== version) {
    return fail('ファイル名と内部の scenarioId または version が一致しません')
  }

  const input = validateFieldSection(root.input, INPUT_FIELD_IDS, 'input')
  const applicationPath = validateField(
    input.applicationPath,
    'input.applicationPath',
  )
  if (
    applicationPath !== undefined &&
    !APPLICATION_PATHS.some((path) => path === applicationPath)
  ) {
    fail('input.applicationPath は P1〜P5 でなければなりません')
  }
  const units = validateCases(root.cases, applicationPath as string | undefined)
  validateComparisonUnits(root.comparisonUnit, scenarioId, units)

  return value as FailureScenarioContract
}

/**
 * 実行結果を契約の case・観測点・実値の期待フィールドへ逐一照合する。
 *
 * 契約が省略理由を書いたフィールドは結果に現れてはならない。到達しない注入点は
 * 呼び出し 0 回、到達する注入点は 1 回以上でなければならない。
 *
 * Args:
 *   contract: 検査済みの故障シナリオ資産契約。
 *   value: シナリオ実行側が返した観測結果。
 *   scope: この runner が担う case と、観測するフィールド(省略時は全部)。
 *     担当外のフィールドは結果に現れてはならない。
 *
 * Raises:
 *   FailureScenarioContractError: 欠落・未知・順序違い・値の不一致がある場合。
 */
export function validateFailureScenarioResult(
  contract: FailureScenarioContract,
  value: unknown,
  scope: Readonly<{
    caseIds?: readonly string[]
    observedFieldIds?: readonly string[]
  }> = {},
): asserts value is FailureScenarioResult {
  const result = requireExactKeys(value, RESULT_FIELD_IDS, 'result')
  if (result.scenarioId !== contract.scenarioId) {
    fail('result.scenarioId が契約と一致しません')
  }
  const { caseIds, observedFieldIds } = scope
  if (
    caseIds?.some(
      (caseId) =>
        !contract.cases.some((testCase) => testCase.caseId === caseId),
    )
  ) {
    fail('資産に無い caseId を担当に指定しています')
  }
  const expectedCases = contract.cases.filter(
    (testCase) => !caseIds || caseIds.includes(testCase.caseId),
  )
  if (
    !Array.isArray(result.cases) ||
    result.cases.length !== expectedCases.length
  ) {
    fail('result.cases の件数が契約と一致しません')
  }

  result.cases.forEach((candidate: unknown, caseIndex: number) => {
    const location = `result.cases[${caseIndex}]`
    const expectedCase = expectedCases[caseIndex]
    const actualCase = requireExactKeys(
      candidate,
      RESULT_CASE_FIELD_IDS,
      location,
    )
    if (!expectedCase || actualCase.caseId !== expectedCase.caseId) {
      fail(`${location}.caseId の順序または値が一致しません`)
    }
    const hookCalls = actualCase.hookCalls
    if (
      typeof hookCalls !== 'number' ||
      !Number.isInteger(hookCalls) ||
      hookCalls < 0
    ) {
      fail(`${location}.hookCalls は 0 以上の整数でなければなりません`)
    }
    const reachability = validateField(
      expectedCase.faultInjection.expectedReachability,
      'expectedReachability',
    )
    if ((reachability === 'unreached') !== (hookCalls === 0)) {
      fail(`${location}.hookCalls が到達性と一致しません`)
    }
    const observations = actualCase.observations
    if (
      !Array.isArray(observations) ||
      observations.length !== expectedCase.observations.length
    ) {
      fail(`${location}.observations の件数が契約と一致しません`)
    }
    observations.forEach(
      (rawObservation: unknown, observationIndex: number) => {
        const observationLocation = `${location}.observations[${observationIndex}]`
        const expected = expectedCase.observations[observationIndex]
        const observation = requireExactKeys(
          rawObservation,
          OBSERVATION_FIELD_IDS,
          observationLocation,
        )
        if (
          !expected ||
          observation.observationPoint !== expected.observationPoint
        ) {
          fail(`${observationLocation} の順序が一致しません`)
        }
        const realFieldIds = Object.keys(expected.fields).filter(
          (fieldId) =>
            !isOmitted(expected.fields[fieldId]) &&
            (!observedFieldIds || observedFieldIds.includes(fieldId)),
        )
        const fields = requireExactKeys(
          observation.fields,
          realFieldIds,
          `${observationLocation}.fields`,
        )
        for (const fieldId of realFieldIds) {
          if (!structurallyEqual(fields[fieldId], expected.fields[fieldId])) {
            fail(`${observationLocation}.fields.${fieldId} が一致しません`)
          }
        }
      },
    )
  })
}

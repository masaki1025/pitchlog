export const FAILURE_SCENARIO_IDS = [
  'multi-tab-single-writer',
  'leader-freeze-reelection',
  'waiting-input-not-accepted',
  'durable-append-failure',
] as const

export type FailureScenarioId = (typeof FAILURE_SCENARIO_IDS)[number]

export const FAILURE_EXPECTED_FIELD_IDS = [
  'queue',
  'd1',
  'lock',
  'acceptanceDisplay',
  'reinputAvailability',
] as const

export type FailureExpectedFieldId = (typeof FAILURE_EXPECTED_FIELD_IDS)[number]

export type FailureScenarioField =
  Readonly<{ value: unknown }> | Readonly<{ omittedBecause: string }>

export type FailureScenarioObservation = Readonly<{
  observationPoint: string
  fields: Readonly<Record<FailureExpectedFieldId, unknown>>
}>

export type FailureScenarioComparisonUnit = Readonly<{
  scenarioId: FailureScenarioId
  observationPoint: string
  expectedField: FailureExpectedFieldId
}>

export type FailureScenarioContract = Readonly<{
  schemaVersion: string | number
  scenarioId: FailureScenarioId
  version: number
  input: Readonly<Record<string, FailureScenarioField>>
  faultInjection: Readonly<Record<string, FailureScenarioField>>
  expected: Readonly<{
    observations: readonly FailureScenarioObservation[]
  }>
  comparisonUnit: readonly FailureScenarioComparisonUnit[]
}>

export type FailureScenarioResult = Readonly<{
  scenarioId: FailureScenarioId
  observations: readonly FailureScenarioObservation[]
}>

const ROOT_FIELD_IDS = [
  'schemaVersion',
  'scenarioId',
  'version',
  'input',
  'faultInjection',
  'expected',
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
] as const

const FAULT_INJECTION_FIELD_IDS = [
  'target',
  'injectionPoint',
  'stopOperation',
  'restartOperation',
] as const

const EXPECTED_SECTION_FIELD_IDS = ['observations'] as const
const OBSERVATION_FIELD_IDS = ['observationPoint', 'fields'] as const
const COMPARISON_UNIT_FIELD_IDS = [
  'scenarioId',
  'observationPoint',
  'expectedField',
] as const
const RESULT_FIELD_IDS = ['scenarioId', 'observations'] as const
const FILE_NAME_PATTERN = /^([a-z0-9]+(?:-[a-z0-9]+)*)_v([1-9]\d*)\.json$/

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

function requireExpectedFieldId(
  value: unknown,
  location: string,
): FailureExpectedFieldId {
  if (
    typeof value !== 'string' ||
    !FAILURE_EXPECTED_FIELD_IDS.some((fieldId) => fieldId === value)
  ) {
    return fail(`${location} は既知の期待フィールドでなければなりません`)
  }
  return value as FailureExpectedFieldId
}

function validateField(value: unknown, location: string): void {
  if (!isRecord(value)) {
    fail(`${location} は値または省略理由を持たなければなりません`)
  }

  const keys = Object.keys(value)
  if (keys.length !== 1) {
    fail(`${location} は値または省略理由の一方だけを持たなければなりません`)
  }
  if (keys[0] === 'value') {
    if (value.value === undefined) {
      fail(`${location} の値を暗黙に省略できません`)
    }
    return
  }
  if (keys[0] === 'omittedBecause') {
    requireNonEmptyString(value.omittedBecause, `${location}.omittedBecause`)
    return
  }
  fail(`${location} に未知のフィールドがあります`)
}

function validateFieldSection(
  value: unknown,
  fieldIds: readonly string[],
  location: string,
): void {
  const section = requireExactKeys(value, fieldIds, location)
  for (const fieldId of fieldIds) {
    validateField(section[fieldId], `${location}.${fieldId}`)
  }
}

function validateSchemaVersion(value: unknown): void {
  const isNonEmptyString = typeof value === 'string' && value.trim().length > 0
  const isPositiveInteger =
    typeof value === 'number' && Number.isInteger(value) && value > 0
  if (!isNonEmptyString && !isPositiveInteger) {
    fail('schemaVersion は空でない文字列または正の整数でなければなりません')
  }
}

function validateObservations(value: unknown): FailureScenarioObservation[] {
  if (!Array.isArray(value) || value.length === 0) {
    return fail('expected.observations は空でない配列でなければなりません')
  }

  const seenObservationPoints = new Set<string>()
  return value.map((candidate, index) => {
    const location = `expected.observations[${index}]`
    const observation = requireExactKeys(
      candidate,
      OBSERVATION_FIELD_IDS,
      location,
    )
    const observationPoint = requireNonEmptyString(
      observation.observationPoint,
      `${location}.observationPoint`,
    )
    if (seenObservationPoints.has(observationPoint)) {
      return fail(`観測点が重複しています: ${observationPoint}`)
    }
    seenObservationPoints.add(observationPoint)

    const fields = requireExactKeys(
      observation.fields,
      FAILURE_EXPECTED_FIELD_IDS,
      `${location}.fields`,
    )
    for (const fieldId of FAILURE_EXPECTED_FIELD_IDS) {
      if (fields[fieldId] === undefined) {
        fail(`${location}.fields.${fieldId} を省略できません`)
      }
      if (
        isRecord(fields[fieldId]) &&
        Object.hasOwn(fields[fieldId], 'omittedBecause')
      ) {
        fail(`${location}.fields.${fieldId} に省略理由は指定できません`)
      }
    }

    return { observationPoint, fields } as FailureScenarioObservation
  })
}

function validateComparisonUnits(
  value: unknown,
  scenarioId: FailureScenarioId,
  observations: readonly FailureScenarioObservation[],
): void {
  if (!Array.isArray(value)) {
    fail('comparisonUnit は配列でなければなりません')
  }

  const expectedUnits = observations.flatMap((observation) =>
    FAILURE_EXPECTED_FIELD_IDS.map((expectedField) => ({
      scenarioId,
      observationPoint: observation.observationPoint,
      expectedField,
    })),
  )
  if (value.length !== expectedUnits.length) {
    fail('comparisonUnit は全観測点と全期待フィールドを含まなければなりません')
  }

  value.forEach((candidate, index) => {
    const unit = requireExactKeys(
      candidate,
      COMPARISON_UNIT_FIELD_IDS,
      `comparisonUnit[${index}]`,
    )
    const expected = expectedUnits[index]
    if (!expected) {
      fail(`comparisonUnit[${index}] は余分な比較単位です`)
    }
    const actualScenarioId = requireScenarioId(
      unit.scenarioId,
      `comparisonUnit[${index}].scenarioId`,
    )
    const actualObservationPoint = requireNonEmptyString(
      unit.observationPoint,
      `comparisonUnit[${index}].observationPoint`,
    )
    const actualExpectedField = requireExpectedFieldId(
      unit.expectedField,
      `comparisonUnit[${index}].expectedField`,
    )
    if (
      actualScenarioId !== expected.scenarioId ||
      actualObservationPoint !== expected.observationPoint ||
      actualExpectedField !== expected.expectedField
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
 * ファイル名と資産の4区分、期待値、比較単位を fail-closed で検査する。
 *
 * Args:
 *   fileName: 版を含むファイル名。
 *   value: JSON から読み込んだ値。
 *
 * Returns:
 *   検査済みの故障シナリオ資産契約。
 *
 * Raises:
 *   FailureScenarioContractError: 未知・欠落・順序違いを含む場合。
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
  validateSchemaVersion(root.schemaVersion)
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

  validateFieldSection(root.input, INPUT_FIELD_IDS, 'input')
  validateFieldSection(
    root.faultInjection,
    FAULT_INJECTION_FIELD_IDS,
    'faultInjection',
  )

  const expected = requireExactKeys(
    root.expected,
    EXPECTED_SECTION_FIELD_IDS,
    'expected',
  )
  const observations = validateObservations(expected.observations)
  validateComparisonUnits(root.comparisonUnit, scenarioId, observations)

  return value as FailureScenarioContract
}

/**
 * 実行結果を契約の観測点と全期待フィールドへ逐一照合する。
 *
 * Args:
 *   contract: 検査済みの故障シナリオ資産契約。
 *   value: シナリオ実行側が返した観測結果。
 *
 * Raises:
 *   FailureScenarioContractError: 欠落・未知・順序違い・余分な結果がある場合。
 */
export function validateFailureScenarioResult(
  contract: FailureScenarioContract,
  value: unknown,
): asserts value is FailureScenarioResult {
  const result = requireExactKeys(value, RESULT_FIELD_IDS, 'result')
  if (result.scenarioId !== contract.scenarioId) {
    fail('result.scenarioId が契約と一致しません')
  }
  const observations = validateObservations(result.observations)
  if (observations.length !== contract.expected.observations.length) {
    fail('result.observations の件数が契約と一致しません')
  }

  observations.forEach((observation, observationIndex) => {
    const expected = contract.expected.observations[observationIndex]
    if (
      !expected ||
      observation.observationPoint !== expected.observationPoint
    ) {
      fail(`result.observations[${observationIndex}] の順序が一致しません`)
    }
    for (const fieldId of FAILURE_EXPECTED_FIELD_IDS) {
      if (
        !structurallyEqual(
          observation.fields[fieldId],
          expected.fields[fieldId],
        )
      ) {
        fail(
          `result.observations[${observationIndex}].fields.${fieldId} が一致しません`,
        )
      }
    }
  })
}

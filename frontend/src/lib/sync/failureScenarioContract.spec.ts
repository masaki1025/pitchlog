import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { describe, expect, it } from 'vitest'
import {
  CLIENT_REQUIRED_FIELD_IDS,
  FAILURE_EXPECTED_FIELD_IDS,
  FAILURE_SCENARIO_IDS,
  FAILURE_SCENARIO_SCHEMA_VERSION,
  parseFailureScenarioContract,
  validateFailureScenarioContract,
  validateFailureScenarioResult,
  type FailureScenarioContract,
  type FailureScenarioId,
} from './failureScenarioContract'

const FIXTURE_DIRECTORY = resolve(
  cwd(),
  '../tests/fixtures/sync-protocol-failures',
)

/** 各 scenarioId の現行版(版を上げたらここを改める — 正本 10-3 の版付け)。 */
const CURRENT_VERSIONS = {
  'multi-tab-single-writer': 2,
  'leader-freeze-reelection': 2,
  'waiting-input-not-accepted': 2,
  'durable-append-failure': 2,
} as const satisfies Record<FailureScenarioId, number>

function currentFileName(scenarioId: FailureScenarioId): string {
  return `${scenarioId}_v${CURRENT_VERSIONS[scenarioId]}.json`
}

function readFixture(fileName: string): string {
  return readFileSync(resolve(FIXTURE_DIRECTORY, fileName), 'utf8')
}

const FIXTURES = FAILURE_SCENARIO_IDS.map((scenarioId) => ({
  fileName: currentFileName(scenarioId),
  source: readFixture(currentFileName(scenarioId)),
}))

type MutableObservation = {
  observationPoint: string
  fields: Record<string, unknown>
}
type MutableCase = {
  caseId: string
  faultInjection: Record<string, unknown>
  observations: MutableObservation[]
}
type MutableAsset = Record<string, unknown> & {
  input: Record<string, unknown>
  cases: MutableCase[]
  comparisonUnit: Record<string, unknown>[]
}
type MutableResult = {
  scenarioId: string
  cases: {
    caseId: string
    hookCalls: number
    observations: MutableObservation[]
  }[]
}

function mutableFixture(scenarioId: FailureScenarioId): MutableAsset {
  return JSON.parse(readFixture(currentFileName(scenarioId))) as MutableAsset
}

function firstObservation(asset: MutableAsset): MutableObservation {
  const observation = asset.cases[0]?.observations[0]
  if (!observation) {
    throw new Error('変異対象の観測点がありません')
  }
  return observation
}

function resultFrom(contract: FailureScenarioContract): MutableResult {
  return {
    scenarioId: contract.scenarioId,
    cases: contract.cases.map((testCase) => ({
      caseId: testCase.caseId,
      hookCalls: 1,
      observations: testCase.observations.map((observation) => ({
        observationPoint: observation.observationPoint,
        fields: Object.fromEntries(
          Object.entries(structuredClone(observation.fields)).filter(
            ([, value]) =>
              !(
                typeof value === 'object' &&
                value !== null &&
                Object.hasOwn(value, 'omittedBecause')
              ),
          ),
        ),
      })),
    })),
  }
}

describe('failureScenarioContract', () => {
  it('現行版の資産すべてを検査し、scenarioId とファイル名を exact-set に閉じる', () => {
    const actualFileNames = readdirSync(FIXTURE_DIRECTORY)
      .filter((fileName) => fileName.endsWith('.json'))
      .sort()
    const contracts = FIXTURES.map(({ fileName, source }) =>
      parseFailureScenarioContract(fileName, source),
    )

    expect(contracts.map((contract) => contract.scenarioId).sort()).toEqual(
      [...FAILURE_SCENARIO_IDS].sort(),
    )
    expect(actualFileNames).toEqual(
      FAILURE_SCENARIO_IDS.map(currentFileName).sort(),
    )
    for (const contract of contracts) {
      expect(contract.schemaVersion).toBe(FAILURE_SCENARIO_SCHEMA_VERSION)
    }
  })

  it('ファイル名と内部 scenarioId・整数 version・schemaVersion を照合する', () => {
    const source = mutableFixture('multi-tab-single-writer')
    const fileName = currentFileName('multi-tab-single-writer')

    expect(() =>
      validateFailureScenarioContract('unknown_v2.json', source),
    ).toThrow()
    expect(() =>
      validateFailureScenarioContract(
        'multi-tab-single-writer_v1.json',
        source,
      ),
    ).toThrow()

    const fractionalVersion = structuredClone(source)
    fractionalVersion.version = 1.5
    expect(() =>
      validateFailureScenarioContract(fileName, fractionalVersion),
    ).toThrow()

    const missingSchemaVersion = structuredClone(source)
    delete missingSchemaVersion.schemaVersion
    expect(() =>
      validateFailureScenarioContract(fileName, missingSchemaVersion),
    ).toThrow()
  })

  it('旧 schemaVersion と新構造・新 schemaVersion と旧構造をいずれも拒否する', () => {
    const fileName = currentFileName('durable-append-failure')
    const oldVersionNewStructure = mutableFixture('durable-append-failure')
    oldVersionNewStructure.schemaVersion = 1
    expect(() =>
      validateFailureScenarioContract(fileName, oldVersionNewStructure),
    ).toThrow(/schemaVersion/)

    const newVersionOldStructure = mutableFixture('durable-append-failure')
    const [testCase] = newVersionOldStructure.cases
    delete (newVersionOldStructure as Record<string, unknown>).cases
    newVersionOldStructure.faultInjection = testCase?.faultInjection
    newVersionOldStructure.expected = { observations: testCase?.observations }
    expect(() =>
      validateFailureScenarioContract(fileName, newVersionOldStructure),
    ).toThrow(/キー/)
  })

  it('入力・case・比較単位を必須にする', () => {
    for (const section of ['input', 'cases', 'comparisonUnit'] as const) {
      const source = mutableFixture('multi-tab-single-writer')
      delete (source as Record<string, unknown>)[section]

      expect(() =>
        validateFailureScenarioContract(
          currentFileName('multi-tab-single-writer'),
          source,
        ),
      ).toThrow()
    }
  })

  it('全観測点が共通の期待フィールド 10 件をこの順で持つ', () => {
    expect(FAILURE_EXPECTED_FIELD_IDS).toHaveLength(10)
    for (const fieldId of FAILURE_EXPECTED_FIELD_IDS) {
      for (const scenarioId of FAILURE_SCENARIO_IDS) {
        const source = mutableFixture(scenarioId)
        delete firstObservation(source).fields[fieldId]

        expect(() =>
          validateFailureScenarioContract(currentFileName(scenarioId), source),
        ).toThrow()
      }
    }
  })

  it.each(CLIENT_REQUIRED_FIELD_IDS)(
    'クライアント側の資産では 10-2 の期待値 %s に省略理由を書けない',
    (fieldId) => {
      for (const scenarioId of FAILURE_SCENARIO_IDS) {
        const source = mutableFixture(scenarioId)
        firstObservation(source).fields[fieldId] = { omittedBecause: '理由' }

        expect(() =>
          validateFailureScenarioContract(currentFileName(scenarioId), source),
        ).toThrow(/省略理由/)
      }
    },
  )

  it('該当しない入力・故障注入・期待フィールドに空でない省略理由を要求する', () => {
    const fileName = currentFileName('waiting-input-not-accepted')
    const input = mutableFixture('waiting-input-not-accepted')
    input.input.d3 = { omittedBecause: '' }
    expect(() => validateFailureScenarioContract(fileName, input)).toThrow()

    const field = mutableFixture('waiting-input-not-accepted')
    firstObservation(field).fields.prefix = { omittedBecause: ' ' }
    expect(() => validateFailureScenarioContract(fileName, field)).toThrow()

    const mixed = mutableFixture('waiting-input-not-accepted')
    firstObservation(mixed).fields.prefix = {
      omittedBecause: '理由',
      value: true,
    }
    expect(() => validateFailureScenarioContract(fileName, mixed)).toThrow(
      /省略表現/,
    )
  })

  it('case の caseId・注入対象・到達性・重複注入を検査する', () => {
    const fileName = currentFileName('leader-freeze-reelection')

    const duplicateCase = mutableFixture('leader-freeze-reelection')
    const [original] = duplicateCase.cases
    if (!original) {
      throw new Error('変異対象の case がありません')
    }
    duplicateCase.cases.push({ ...structuredClone(original), caseId: 'again' })
    expect(() =>
      validateFailureScenarioContract(fileName, duplicateCase),
    ).toThrow(/同じ注入/)

    const unknownKind = mutableFixture('leader-freeze-reelection')
    const unknownCase = unknownKind.cases[0]
    if (unknownCase) {
      unknownCase.faultInjection.target = {
        value: { kind: 'server', operation: '停止' },
      }
    }
    expect(() =>
      validateFailureScenarioContract(fileName, unknownKind),
    ).toThrow(/kind/)

    const transactionWithoutPath = mutableFixture('leader-freeze-reelection')
    const transactionCase = transactionWithoutPath.cases[0]
    if (transactionCase) {
      transactionCase.faultInjection.target = {
        value: { kind: 'transaction', path: 'P1', tElement: 'T2' },
      }
    }
    expect(() =>
      validateFailureScenarioContract(fileName, transactionWithoutPath),
    ).toThrow(/applicationPath/)

    const unknownReachability = mutableFixture('leader-freeze-reelection')
    const reachabilityCase = unknownReachability.cases[0]
    if (reachabilityCase) {
      reachabilityCase.faultInjection.expectedReachability = { value: 'maybe' }
    }
    expect(() =>
      validateFailureScenarioContract(fileName, unknownReachability),
    ).toThrow(/expectedReachability/)

    const badCaseId = mutableFixture('leader-freeze-reelection')
    const badCase = badCaseId.cases[0]
    if (badCase) {
      badCase.caseId = 'Freeze'
    }
    expect(() => validateFailureScenarioContract(fileName, badCaseId)).toThrow(
      /caseId/,
    )
  })

  it('comparisonUnit を case・観測点・全期待フィールドの順序付き直積に閉じる', () => {
    for (const fixture of FIXTURES) {
      const contract = parseFailureScenarioContract(
        fixture.fileName,
        fixture.source,
      )
      const fieldCount = contract.cases.reduce(
        (total, testCase) =>
          total +
          testCase.observations.reduce(
            (sum, observation) => sum + Object.keys(observation.fields).length,
            0,
          ),
        0,
      )
      expect(contract.comparisonUnit).toHaveLength(fieldCount)
    }

    const fileName = currentFileName('leader-freeze-reelection')
    const swapped = mutableFixture('leader-freeze-reelection')
    const [first, second] = swapped.comparisonUnit
    if (!first || !second) {
      throw new Error('変異対象の比較単位がありません')
    }
    swapped.comparisonUnit[0] = second
    swapped.comparisonUnit[1] = first
    expect(() => validateFailureScenarioContract(fileName, swapped)).toThrow()

    const isolated = mutableFixture('leader-freeze-reelection')
    const [unit] = isolated.comparisonUnit
    if (unit) {
      unit.observationPoint = 'どの case にも無い観測点'
    }
    expect(() => validateFailureScenarioContract(fileName, isolated)).toThrow(
      /comparisonUnit/,
    )

    const wrongTarget = mutableFixture('leader-freeze-reelection')
    const [targetUnit] = wrongTarget.comparisonUnit
    if (targetUnit) {
      targetUnit.injectionTarget = 'client:別の操作'
    }
    expect(() =>
      validateFailureScenarioContract(fileName, wrongTarget),
    ).toThrow(/comparisonUnit/)
  })

  it('未知フィールドを fail-closed で拒否する', () => {
    const fileName = currentFileName('durable-append-failure')
    const injection = mutableFixture('durable-append-failure')
    const injectionCase = injection.cases[0]
    if (injectionCase) {
      injectionCase.faultInjection.unknown = { value: true }
    }
    expect(() => validateFailureScenarioContract(fileName, injection)).toThrow()

    const field = mutableFixture('durable-append-failure')
    firstObservation(field).fields.unknown = { value: true }
    expect(() => validateFailureScenarioContract(fileName, field)).toThrow()
  })

  it('結果比較で欠落・未知・順序・余分な永続化・省略の混入・到達性を拒否する', () => {
    const contract = parseFailureScenarioContract(
      currentFileName('leader-freeze-reelection'),
      readFixture(currentFileName('leader-freeze-reelection')),
    )
    const validResult = resultFrom(contract)
    expect(() =>
      validateFailureScenarioResult(contract, validResult),
    ).not.toThrow()

    const mutations: ((result: MutableResult) => void)[] = [
      (result) => {
        delete result.cases[0]?.observations[0]?.fields.queue
      },
      (result) => {
        const observation = result.cases[0]?.observations[0]
        if (observation) {
          observation.fields.unknown = true
        }
      },
      (result) => {
        result.cases[0]?.observations.reverse()
      },
      (result) => {
        const queue = result.cases[0]?.observations[0]?.fields.queue
        if (typeof queue === 'object' && queue !== null) {
          ;(queue as Record<string, unknown>).extraPersistence = true
        }
      },
      (result) => {
        const observation = result.cases[0]?.observations[0]
        if (observation) {
          observation.fields.prefix = { omittedBecause: '理由' }
        }
      },
      (result) => {
        const testCase = result.cases[0]
        if (testCase) {
          testCase.hookCalls = 0
        }
      },
      (result) => {
        const testCase = result.cases[0]
        if (testCase) {
          testCase.caseId = 'other-case'
        }
      },
    ]
    for (const mutate of mutations) {
      const result = structuredClone(validResult)
      mutate(result)
      expect(() => validateFailureScenarioResult(contract, result)).toThrow()
    }
  })
})

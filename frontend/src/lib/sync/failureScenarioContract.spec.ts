import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { cwd } from 'node:process'
import { describe, expect, it } from 'vitest'
import {
  FAILURE_EXPECTED_FIELD_IDS,
  FAILURE_SCENARIO_IDS,
  parseFailureScenarioContract,
  validateFailureScenarioContract,
  validateFailureScenarioResult,
  type FailureScenarioContract,
} from './failureScenarioContract'

const FIXTURE_DIRECTORY = resolve(
  cwd(),
  '../tests/fixtures/sync-protocol-failures',
)

function readFixture(fileName: string): string {
  return readFileSync(resolve(FIXTURE_DIRECTORY, fileName), 'utf8')
}

const FIXTURES = [
  {
    fileName: 'multi-tab-single-writer_v1.json',
    source: readFixture('multi-tab-single-writer_v1.json'),
  },
  {
    fileName: 'leader-freeze-reelection_v1.json',
    source: readFixture('leader-freeze-reelection_v1.json'),
  },
  {
    fileName: 'waiting-input-not-accepted_v1.json',
    source: readFixture('waiting-input-not-accepted_v1.json'),
  },
  {
    fileName: 'durable-append-failure_v1.json',
    source: readFixture('durable-append-failure_v1.json'),
  },
] as const

function mutableFixture(fileName: (typeof FIXTURES)[number]['fileName']) {
  const fixture = FIXTURES.find((candidate) => candidate.fileName === fileName)
  if (!fixture) {
    throw new Error(`故障シナリオ資産が見つかりません: ${fileName}`)
  }
  return JSON.parse(fixture.source) as Record<string, unknown>
}

function resultFrom(
  contract: FailureScenarioContract,
): Record<string, unknown> {
  return {
    scenarioId: contract.scenarioId,
    observations: structuredClone(contract.expected.observations),
  }
}

describe('failureScenarioContract', () => {
  it('版付きの4資産すべてを検査し、scenarioId を exact-set に閉じる', () => {
    const actualFileNames = readdirSync(FIXTURE_DIRECTORY)
      .filter((fileName) => fileName.endsWith('.json'))
      .sort()
    const contracts = FIXTURES.map(({ fileName, source }) =>
      parseFailureScenarioContract(fileName, source),
    )

    expect(contracts).toHaveLength(4)
    expect(contracts.map((contract) => contract.scenarioId).sort()).toEqual(
      [...FAILURE_SCENARIO_IDS].sort(),
    )
    const expectedFileNames = FAILURE_SCENARIO_IDS.map(
      (scenarioId) => `${scenarioId}_v1.json`,
    ).sort()
    expect(actualFileNames).toEqual(expectedFileNames)
    expect(FIXTURES.map((fixture) => fixture.fileName).sort()).toEqual(
      expectedFileNames,
    )
  })

  it('ファイル名と内部 scenarioId・整数 version・schemaVersion を照合する', () => {
    const source = mutableFixture('multi-tab-single-writer_v1.json')

    expect(() =>
      validateFailureScenarioContract('unknown_v1.json', source),
    ).toThrow()

    const fractionalVersion = structuredClone(source)
    fractionalVersion.version = 1.5
    expect(() =>
      validateFailureScenarioContract(
        'multi-tab-single-writer_v1.json',
        fractionalVersion,
      ),
    ).toThrow()

    const missingSchemaVersion = structuredClone(source)
    delete missingSchemaVersion.schemaVersion
    expect(() =>
      validateFailureScenarioContract(
        'multi-tab-single-writer_v1.json',
        missingSchemaVersion,
      ),
    ).toThrow()
  })

  it('入力・故障注入・期待結果・比較単位の4区分を必須にする', () => {
    for (const section of [
      'input',
      'faultInjection',
      'expected',
      'comparisonUnit',
    ] as const) {
      const source = mutableFixture('multi-tab-single-writer_v1.json')
      delete source[section]

      expect(() =>
        validateFailureScenarioContract(
          'multi-tab-single-writer_v1.json',
          source,
        ),
      ).toThrow()
    }
  })

  it.each(FAILURE_EXPECTED_FIELD_IDS)(
    '10-2 の期待値 %s を全観測点で省略できない',
    (fieldId) => {
      for (const fixture of FIXTURES) {
        const source = mutableFixture(fixture.fileName)
        const expected = source.expected as {
          observations: { fields: Record<string, unknown> }[]
        }
        delete expected.observations[0]?.fields[fieldId]

        expect(() =>
          validateFailureScenarioContract(fixture.fileName, source),
        ).toThrow()
      }
    },
  )

  it('該当しない入力・故障注入フィールドに空でない省略理由を要求する', () => {
    const source = mutableFixture('waiting-input-not-accepted_v1.json')
    const input = source.input as Record<string, unknown>
    input.d3 = { omittedBecause: '' }

    expect(() =>
      validateFailureScenarioContract(
        'waiting-input-not-accepted_v1.json',
        source,
      ),
    ).toThrow()
  })

  it('comparisonUnit を scenarioId・観測点・全期待フィールドの順序付き直積に閉じる', () => {
    for (const fixture of FIXTURES) {
      const contract = parseFailureScenarioContract(
        fixture.fileName,
        fixture.source,
      )
      expect(contract.comparisonUnit).toHaveLength(
        contract.expected.observations.length *
          FAILURE_EXPECTED_FIELD_IDS.length,
      )
    }

    const source = mutableFixture('leader-freeze-reelection_v1.json')
    const comparisonUnit = source.comparisonUnit as unknown[]
    const first = comparisonUnit[0]
    const second = comparisonUnit[1]
    comparisonUnit[0] = second
    comparisonUnit[1] = first

    expect(() =>
      validateFailureScenarioContract(
        'leader-freeze-reelection_v1.json',
        source,
      ),
    ).toThrow()
  })

  it('未知フィールドを fail-closed で拒否する', () => {
    const source = mutableFixture('durable-append-failure_v1.json')
    const faultInjection = source.faultInjection as Record<string, unknown>
    faultInjection.unknown = { value: true }

    expect(() =>
      validateFailureScenarioContract('durable-append-failure_v1.json', source),
    ).toThrow()
  })

  it('結果比較で欠落・未知・観測点順序・余分な永続化を拒否する', () => {
    const contract = parseFailureScenarioContract(
      'leader-freeze-reelection_v1.json',
      readFixture('leader-freeze-reelection_v1.json'),
    )
    const validResult = resultFrom(contract)
    expect(() =>
      validateFailureScenarioResult(contract, validResult),
    ).not.toThrow()

    const missingField = structuredClone(validResult)
    const missingObservations = missingField.observations as {
      fields: Record<string, unknown>
    }[]
    delete missingObservations[0]?.fields.queue
    expect(() =>
      validateFailureScenarioResult(contract, missingField),
    ).toThrow()

    const unknownField = structuredClone(validResult)
    const unknownObservations = unknownField.observations as {
      fields: Record<string, unknown>
    }[]
    if (unknownObservations[0]) {
      unknownObservations[0].fields.unknown = true
    }
    expect(() =>
      validateFailureScenarioResult(contract, unknownField),
    ).toThrow()

    const reordered = structuredClone(validResult)
    const reorderedObservations = reordered.observations as unknown[]
    reordered.observations = [...reorderedObservations].reverse()
    expect(() => validateFailureScenarioResult(contract, reordered)).toThrow()

    const extraPersistence = structuredClone(validResult)
    const extraPersistenceObservations = extraPersistence.observations as {
      fields: Record<string, unknown>
    }[]
    const queue = extraPersistenceObservations[0]?.fields.queue
    if (typeof queue === 'object' && queue !== null) {
      ;(queue as Record<string, unknown>).extraPersistence = true
    }
    expect(() =>
      validateFailureScenarioResult(contract, extraPersistence),
    ).toThrow()
  })
})

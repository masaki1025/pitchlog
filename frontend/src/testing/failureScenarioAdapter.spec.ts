import { describe, expect, it } from 'vitest'
import * as ts from 'typescript'
import {
  FAILURE_SCENARIO_IDS,
  validateFailureScenarioResult,
  type FailureScenarioContract,
  type FailureScenarioResult,
} from '../lib/sync/failureScenarioContract'
import failureScenarioAdapterSource from './failureScenarioAdapter.ts?raw'
import {
  executeFailureScenario,
  readFailureScenarioAssets,
} from './failureScenarioAdapter'

type MutableObservation = {
  observationPoint: string
  fields: Record<string, unknown>
}
type MutableResult = {
  scenarioId: string
  observations: MutableObservation[]
}
type ScalarLiteral = string | number | boolean

const contracts = readFailureScenarioAssets()

function contractById(
  scenarioId: FailureScenarioContract['scenarioId'],
): FailureScenarioContract {
  const contract = contracts.find(
    (candidate) => candidate.scenarioId === scenarioId,
  )
  if (!contract) {
    throw new Error(`故障シナリオ資産が見つかりません: ${scenarioId}`)
  }
  return contract
}

function mutableResult(result: FailureScenarioResult): MutableResult {
  return structuredClone(result) as unknown as MutableResult
}

function collectScalarLiterals(
  value: unknown,
  destination: ScalarLiteral[],
): void {
  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    destination.push(value)
    return
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      collectScalarLiterals(item, destination)
    }
    return
  }
  if (typeof value === 'object' && value !== null) {
    for (const item of Object.values(value)) {
      collectScalarLiterals(item, destination)
    }
  }
}

function sourceScalarLiterals(source: string): ScalarLiteral[] {
  const sourceFile = ts.createSourceFile(
    'failureScenarioAdapter.ts',
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  )
  const literals: ScalarLiteral[] = []

  function visit(node: ts.Node): void {
    if (ts.isStringLiteralLike(node)) {
      literals.push(node.text)
    } else if (ts.isNumericLiteral(node)) {
      literals.push(Number(node.text))
    } else if (node.kind === ts.SyntaxKind.TrueKeyword) {
      literals.push(true)
    } else if (node.kind === ts.SyntaxKind.FalseKeyword) {
      literals.push(false)
    }
    ts.forEachChild(node, visit)
  }
  visit(sourceFile)
  return literals
}

function scalarKey(value: ScalarLiteral): string {
  return `${typeof value}:${String(value)}`
}

describe('failureScenarioAdapter', () => {
  it.each(contracts)(
    '$scenarioId の資産入力で製品コードを実行し、全比較単位を満たす',
    async (contract) => {
      const result = await executeFailureScenario(contract)

      expect(() =>
        validateFailureScenarioResult(contract, result),
      ).not.toThrow()
    },
  )

  it('4 資産を過不足なく読み、期待値をアダプタへ複製しない', () => {
    const expectedLiterals: ScalarLiteral[] = []
    for (const contract of contracts) {
      collectScalarLiterals(contract.expected, expectedLiterals)
    }
    const sourceLiterals = sourceScalarLiterals(failureScenarioAdapterSource)
    const duplicatedLiterals = expectedLiterals.filter((expectedLiteral) =>
      sourceLiterals.some((sourceLiteral) =>
        typeof expectedLiteral === 'string' && typeof sourceLiteral === 'string'
          ? sourceLiteral.includes(expectedLiteral)
          : scalarKey(sourceLiteral) === scalarKey(expectedLiteral),
      ),
    )

    expect(contracts).toHaveLength(FAILURE_SCENARIO_IDS.length)
    expect(contracts.map((contract) => contract.scenarioId).sort()).toEqual(
      [...FAILURE_SCENARIO_IDS].sort(),
    )
    expect(failureScenarioAdapterSource).not.toMatch(/\bexpected\b/)
    expect(duplicatedLiterals).toEqual([])
  })

  it('期待フィールドを一つ削った実行結果を red にする', async () => {
    const [, scenarioId] = FAILURE_SCENARIO_IDS
    const contract = contractById(scenarioId)
    const result = mutableResult(await executeFailureScenario(contract))
    const [firstObservation] = result.observations
    if (!firstObservation) {
      throw new Error('変異対象の観測結果がありません')
    }
    delete firstObservation.fields.queue

    expect(() => validateFailureScenarioResult(contract, result)).toThrow()
  })

  it('未知フィールドを足した実行結果を red にする', async () => {
    const [, scenarioId] = FAILURE_SCENARIO_IDS
    const contract = contractById(scenarioId)
    const result = mutableResult(await executeFailureScenario(contract))
    const [firstObservation] = result.observations
    if (!firstObservation) {
      throw new Error('変異対象の観測結果がありません')
    }
    firstObservation.fields.unknown = true

    expect(() => validateFailureScenarioResult(contract, result)).toThrow()
  })

  it('観測点の順序を入れ替えた実行結果を red にする', async () => {
    const [, scenarioId] = FAILURE_SCENARIO_IDS
    const contract = contractById(scenarioId)
    const result = mutableResult(await executeFailureScenario(contract))
    result.observations.reverse()

    expect(() => validateFailureScenarioResult(contract, result)).toThrow()
  })

  it('余分な永続化を実際に起こした観測結果を red にする', async () => {
    const [, , , scenarioId] = FAILURE_SCENARIO_IDS
    const contract = contractById(scenarioId)
    const result = await executeFailureScenario(contract, {
      extraPersistence: true,
    })

    expect(() => validateFailureScenarioResult(contract, result)).toThrow()
  })
})

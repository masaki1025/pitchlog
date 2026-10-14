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
  CLIENT_RUNNER_SCENARIO_IDS,
  SERVER_RUNNER_SCENARIO_IDS,
  executeFailureScenario,
  readFailureScenarioAssets,
} from './failureScenarioAdapter'

type MutableObservation = {
  observationPoint: string
  fields: Record<string, unknown>
}
type MutableResult = {
  scenarioId: string
  cases: {
    caseId: string
    hookCalls: number
    observations: MutableObservation[]
  }[]
}
type ScalarLiteral = string | number | boolean

const contracts = readFailureScenarioAssets()
const clientContracts = contracts.filter((contract) =>
  CLIENT_RUNNER_SCENARIO_IDS.includes(contract.scenarioId),
)

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

function observationsOf(result: MutableResult): MutableObservation[] {
  const [testCase] = result.cases
  if (!testCase) {
    throw new Error('変異対象の case がありません')
  }
  return testCase.observations
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
  it.each(clientContracts)(
    '$scenarioId の資産入力で製品コードを実行し、全比較単位を満たす',
    async (contract) => {
      const result = await executeFailureScenario(contract)

      expect(() =>
        validateFailureScenarioResult(contract, result),
      ).not.toThrow()
    },
  )

  it('クライアント runner とサーバー runner の分担を exact-set に閉じる', () => {
    const client = new Set<string>(CLIENT_RUNNER_SCENARIO_IDS)
    const server = new Set<string>(SERVER_RUNNER_SCENARIO_IDS)

    expect([...client].filter((scenarioId) => server.has(scenarioId))).toEqual(
      [],
    )
    expect([...client, ...server].sort()).toEqual(
      [...FAILURE_SCENARIO_IDS].sort(),
    )
    for (const contract of contracts) {
      const hasApplicationPath = Object.hasOwn(
        contract.input.applicationPath ?? {},
        'value',
      )
      expect(server.has(contract.scenarioId)).toBe(hasApplicationPath)
    }
  })

  it('全資産を過不足なく読み、期待値をアダプタへ複製しない', () => {
    const expectedLiterals: ScalarLiteral[] = []
    for (const contract of clientContracts) {
      for (const testCase of contract.cases) {
        for (const observation of testCase.observations) {
          collectScalarLiterals(observation.fields, expectedLiterals)
        }
      }
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
    const [firstObservation] = observationsOf(result)
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
    const [firstObservation] = observationsOf(result)
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
    observationsOf(result).reverse()

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

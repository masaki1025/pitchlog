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
  CLIENT_OBSERVED_CASES,
  CLIENT_RUNNER_SCENARIO_IDS,
  clientObservedFieldIds,
  SERVER_RUNNER_SCENARIO_IDS,
  executeClientObservedCase,
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

/**
 * 端末のキューが正本 7-2 の読み(拒否 → 要操作)と食い違う既知の観測点。
 *
 * B4 の要求の中の B3b 候補はサーバーが A5「拒否」で返すが、境界が B4 なので B3 の
 * 理由の分類が届かず、端末のキュー遷移は未送信のまま残す。正本 11-4(B4 は段階 ⑤ で
 * 確定し DI5 の射程外)と 10-2 の混在バッチの行の読みが分かれるため、確定ゲートで
 * 問う(worklog)。決着したら資産か製品を直し、この表から外す。
 */
const KNOWN_QUEUE_DIVERGENCES = [
  {
    scenarioId: 'd1-mixed-batch',
    caseId: 'ack-loss-handover',
    observationIndex: 1,
    d1: 2,
    actual: [2, '未送信', null],
  },
] as const
const clientContracts = contracts.filter((contract) =>
  CLIENT_RUNNER_SCENARIO_IDS.includes(contract.scenarioId),
)
// サーバー側の資産のうち、端末の状態(I6・キュー)をこのアダプタが観測する case。
const clientObservedCases = contracts.flatMap((contract) =>
  CLIENT_RUNNER_SCENARIO_IDS.includes(contract.scenarioId)
    ? []
    : contract.cases
        .map((testCase) => ({
          scenarioId: contract.scenarioId,
          caseId: testCase.caseId,
          fieldIds: clientObservedFieldIds(contract, testCase.caseId),
        }))
        .filter(({ fieldIds }) => fieldIds.length),
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
    for (const assigned of CLIENT_OBSERVED_CASES) {
      const testCase = contractById(assigned.scenarioId).cases.find(
        (candidate) => candidate.caseId === assigned.caseId,
      )
      for (const observation of testCase?.observations ?? []) {
        for (const fieldId of assigned.fieldIds) {
          collectScalarLiterals(observation.fields[fieldId], expectedLiterals)
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

  it.each(clientObservedCases)(
    '$scenarioId の $caseId で端末の状態を製品の永続キューから観測し、担当フィールドを満たす',
    async ({ scenarioId, caseId, fieldIds }) => {
      const contract = contractById(scenarioId)
      const result = mutableResult(
        await executeClientObservedCase(contract, caseId),
      )
      const expectedCase = contract.cases.find(
        (candidate) => candidate.caseId === caseId,
      )
      for (const known of KNOWN_QUEUE_DIVERGENCES) {
        if (known.scenarioId !== scenarioId || known.caseId !== caseId) {
          continue
        }
        const queue = result.cases[0]?.observations[known.observationIndex]
          ?.fields.queue as { states: unknown[][] }
        const expectedQueue = expectedCase?.observations[known.observationIndex]
          ?.fields.queue as { states: unknown[][] }
        const index = queue.states.findIndex(([d1]) => d1 === known.d1)
        // 既知の食い違いの 1 行だけが資産と違うことを確かめ、その行を資産の値へ戻す。
        expect(queue.states[index]).toEqual(known.actual)
        expect(expectedQueue.states[index]).not.toEqual(known.actual)
        queue.states[index] = expectedQueue.states[index] ?? []
      }

      expect(() =>
        validateFailureScenarioResult(contract, result, {
          caseIds: [caseId],
          observedFieldIds: fieldIds,
        }),
      ).not.toThrow()
    },
  )

  it('端末を観測するフィールドは case の I6・キューの実値フィールドと一致する', () => {
    expect(clientObservedCases.length).toBeGreaterThan(
      CLIENT_OBSERVED_CASES.length,
    )
    for (const contract of contracts) {
      if (CLIENT_RUNNER_SCENARIO_IDS.includes(contract.scenarioId)) {
        continue
      }
      for (const testCase of contract.cases) {
        const fieldIds = clientObservedFieldIds(contract, testCase.caseId)
        for (const observation of testCase.observations) {
          const real = Object.entries(observation.fields)
            .filter(
              ([fieldId, value]) =>
                (fieldId.startsWith('i6') || fieldId === 'queue') &&
                !(
                  typeof value === 'object' &&
                  value !== null &&
                  Object.hasOwn(value, 'omittedBecause')
                ),
            )
            .map(([fieldId]) => fieldId)
          expect([...fieldIds].sort()).toEqual(real.sort())
        }
      }
    }
    for (const { scenarioId, caseId, fieldIds } of CLIENT_OBSERVED_CASES) {
      expect(SERVER_RUNNER_SCENARIO_IDS).toContain(scenarioId)
      const testCase = contractById(scenarioId).cases.find(
        (candidate) => candidate.caseId === caseId,
      )
      expect(testCase).toBeDefined()
      for (const observation of testCase?.observations ?? []) {
        const i6Fields = Object.entries(observation.fields)
          .filter(
            ([fieldId, value]) =>
              fieldId.startsWith('i6') &&
              !(
                typeof value === 'object' &&
                value !== null &&
                Object.hasOwn(value, 'omittedBecause')
              ),
          )
          .map(([fieldId]) => fieldId)
        expect([...fieldIds].sort()).toEqual(i6Fields.sort())
      }
    }
  })

  it('負例: ACK を端末へ届けない変異は、キューの観測で red にする', async () => {
    const contract = contractById('p1-crash-boundaries')
    const [caseId] = contract.cases.map((testCase) => testCase.caseId)
    if (!caseId) {
      throw new Error('変異対象の case がありません')
    }
    const result = await executeClientObservedCase(contract, caseId, {
      skipAckDelivery: true,
    })

    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: [caseId],
        observedFieldIds: clientObservedFieldIds(contract, caseId),
      }),
    ).toThrow()
  })

  it('負例: 注入の前に I6 を端末へ永続化する変異を red にする', async () => {
    const [{ scenarioId, caseId, fieldIds }] = CLIENT_OBSERVED_CASES
    const contract = contractById(scenarioId)
    const result = await executeClientObservedCase(contract, caseId, {
      persistI6BeforeInjection: true,
    })

    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: [caseId],
        observedFieldIds: fieldIds,
      }),
    ).toThrow()
  })

  it('負例: 永続化の確定後に終了する case で I6 を永続化しない変異を red にする', async () => {
    const assigned = CLIENT_OBSERVED_CASES.find(
      (candidate) => candidate.caseId === 'i6-persisted-then-closed',
    )
    if (!assigned) {
      throw new Error('永続化が成立する I6 の case がありません')
    }
    const contract = contractById(assigned.scenarioId)
    const result = await executeClientObservedCase(contract, assigned.caseId, {
      skipI6Persistence: true,
    })

    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: [assigned.caseId],
        observedFieldIds: assigned.fieldIds,
      }),
    ).toThrow()
  })

  it('担当外の case・フィールドを結果に混ぜると red にする', async () => {
    const [{ scenarioId, caseId, fieldIds }] = CLIENT_OBSERVED_CASES
    const contract = contractById(scenarioId)
    const result = mutableResult(
      await executeClientObservedCase(contract, caseId),
    )
    const [firstCase] = result.cases
    const [firstObservation] = firstCase?.observations ?? []
    if (!firstObservation) {
      throw new Error('変異対象の観測結果がありません')
    }
    firstObservation.fields.recordingRight = { held: true }

    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: [caseId],
        observedFieldIds: fieldIds,
      }),
    ).toThrow()
    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: ['unknown-case'],
        observedFieldIds: fieldIds,
      }),
    ).toThrow()
  })
})

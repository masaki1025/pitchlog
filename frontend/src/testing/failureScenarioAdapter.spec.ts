import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as ts from 'typescript'
import {
  FAILURE_SCENARIO_IDS,
  validateFailureScenarioContract,
  validateFailureScenarioResult,
  type FailureScenarioContract,
  type FailureScenarioResult,
} from '../lib/sync/failureScenarioContract'
import failureScenarioAdapterSource from './failureScenarioAdapter.ts?raw'
import {
  CLIENT_OBSERVED_CASES,
  CLIENT_RUNNER_SCENARIO_IDS,
  FAILURE_FIXTURE_DIRECTORY,
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
const population = JSON.parse(
  readFileSync(
    resolve(
      FAILURE_FIXTURE_DIRECTORY,
      'population',
      'sync-protocol-population_v2.json',
    ),
    'utf8',
  ),
) as {
  schemaVersion: number
  rows: {
    observationKey: string
    scenarioId: string
    status: string
    owner?: string
  }[]
}

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
  it('B3b の理由を欠いた資産を拒否する', () => {
    const asset = structuredClone(
      contractById('p5-b3b-unreached-t9'),
    ) as unknown as {
      cases: { observations: { fields: Record<string, unknown> }[] }[]
    }
    const idempotent = asset.cases[0]!.observations[0]!.fields
      .idempotentResult as Record<string, unknown>
    idempotent.responseReason = null
    expect(() =>
      validateFailureScenarioContract('p5-b3b-unreached-t9_v1.json', asset),
    ).toThrow()
  })
  it('D1 付き経路のロック・表示・再入力可否の省略を拒否する', () => {
    for (const fieldId of [
      'lock',
      'acceptanceDisplay',
      'reinputAvailability',
    ]) {
      const asset = structuredClone(
        contractById('p1-crash-boundaries'),
      ) as unknown as {
        cases: { observations: { fields: Record<string, unknown> }[] }[]
      }
      asset.cases[0]!.observations[0]!.fields[fieldId] = {
        omittedBecause: 'runner が見ない',
      }
      expect(() =>
        validateFailureScenarioContract('p1-crash-boundaries_v1.json', asset),
      ).toThrow()
    }
  })
  it('母集合の単一表を読み、所有資産と観点のペアを照合する', () => {
    const rows = population.rows
    const pairs = rows.map((row) => `${row.observationKey}:${row.scenarioId}`)
    expect(population.schemaVersion).toBe(1)
    expect(rows).toHaveLength(27)
    expect(new Set(pairs).size).toBe(rows.length)
    expect(new Set(rows.map((row) => row.scenarioId)).size).toBe(rows.length)
    expect(new Set(rows.map((row) => row.observationKey)).size).toBe(23)
    expect(
      rows.every((row) => row.status === 'owned' || row.status === 'deferred'),
    ).toBe(true)
    const deferredRows = rows.filter((row) => row.status === 'deferred')
    expect(deferredRows).toHaveLength(11)
    expect(
      deferredRows
        .filter((row) => row.scenarioId !== 'o5-invariant-violation')
        .every((row) => row.owner === 'U-R1(TSK-392)'),
    ).toBe(true)
    expect(
      deferredRows.find((row) => row.scenarioId === 'o5-invariant-violation'),
    ).toEqual({
      observationKey: 'o5-deterministic-invariant',
      scenarioId: 'o5-invariant-violation',
      status: 'deferred',
      owner: 'TSK-506 への接続契約(us1-sync-port-surface)のステップ 14',
    })
    expect(
      new Set(
        rows
          .filter((row) => row.status === 'owned')
          .map((row) => row.scenarioId),
      ),
    ).toEqual(new Set(FAILURE_SCENARIO_IDS))
    expect(new Set(contracts.map((contract) => contract.scenarioId))).toEqual(
      new Set(FAILURE_SCENARIO_IDS),
    )
  })
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
      expect(() =>
        validateFailureScenarioResult(contract, result, {
          caseIds: [caseId],
          observedFieldIds: fieldIds,
        }),
      ).not.toThrow()
    },
  )

  it('負例: 再送選択器の D3 比較を >= に変えると混在バッチの期待値に反する', async () => {
    const contract = contractById('d1-mixed-batch')
    const caseId = 'ack-loss-handover'
    const isD1AfterD3 = vi.fn((d1: number, d3: unknown) => d1 >= Number(d3))
    const result = await executeClientObservedCase(contract, caseId, {
      resendD1AfterD3Override: isD1AfterD3,
    })

    expect(isD1AfterD3).toHaveBeenCalledWith(2, 2)
    expect(
      result.cases[0]?.observations[1]?.fields.reinputAvailability,
    ).toEqual({
      reinputRequired: false,
      automaticResendD1s: [2],
      correctionRequiredD1s: [],
    })
    expect(() =>
      validateFailureScenarioResult(contract, result, {
        caseIds: [caseId],
        observedFieldIds: clientObservedFieldIds(contract, caseId),
      }),
    ).toThrow()
  })

  it('端末を観測するフィールドは case の I6・キュー・ロック・表示の実値と一致する', () => {
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
                (fieldId.startsWith('i6') ||
                  [
                    'queue',
                    'lock',
                    'acceptanceDisplay',
                    'reinputAvailability',
                  ].includes(fieldId)) &&
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

  it('負例: 端末へ渡す acceptedAt を共有応答と異なる値にすると red になる', async () => {
    const assigned = CLIENT_OBSERVED_CASES.find(
      (candidate) => candidate.caseId === 'i6-persisted-then-closed',
    )
    if (!assigned) {
      throw new Error('I6 の永続化 case がありません')
    }
    const contract = contractById(assigned.scenarioId)
    const result = await executeClientObservedCase(contract, assigned.caseId, {
      i6AcceptedAtOverride: '2026-10-16T00:00:00+00:00',
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

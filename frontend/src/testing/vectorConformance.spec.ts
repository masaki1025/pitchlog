import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { isDeepStrictEqual } from 'node:util'
import { expect, it, vi } from 'vitest'
import {
  DEFAULT_RESPONSE_TIMEOUT_MS,
  runVectors,
  UnsupportedVectorCase,
  VectorRunError,
  type CalculationAdapter,
  type GeneratedNormalizer,
  type VectorContract,
} from './vectorRunner'

vi.setConfig({ testTimeout: 3 * DEFAULT_RESPONSE_TIMEOUT_MS + 5_000 })

type Scenario = Readonly<{
  id: string
  description: string
  contract: Omit<VectorContract, 'runner'>
  normalizer: Readonly<{
    generatedId: string
    sourceHash: string
    mode: 'table' | 'passthrough'
    table: readonly Readonly<{ raw: unknown; normalized: unknown }>[]
  }>
  calculation: Readonly<{
    supportedCaseIds: readonly string[]
    outputs?: Readonly<Record<string, unknown>>
  }>
  cases: unknown
  expected:
    | Readonly<{
        outcome: 'complete'
        declaredCaseIds: readonly string[]
        consumedCaseIds: readonly string[]
      }>
    | Readonly<{ outcome: 'vector-run-error'; messagePrefix: string }>
  trace: Readonly<{
    normalizeCalls: number
    executedCaseIds: readonly string[]
  }>
}>

const REPOSITORY_ROOT = resolve(process.cwd(), '..')
const fixture = JSON.parse(
  readFileSync(
    resolve(
      REPOSITORY_ROOT,
      'tests/domain/runners/fixtures/vector-conformance/vector_conformance_v1.json',
    ),
    'utf8',
  ),
) as Readonly<{ scenarios: readonly Scenario[] }>
const scenarios = fixture.scenarios
const consumedScenarioIds = new Set<string>()

it.each(scenarios)('$id: $description', async (scenario) => {
  let normalizeCalls = 0
  const executedCaseIds: string[] = []
  const normalizer: GeneratedNormalizer = {
    generatedId: scenario.normalizer.generatedId,
    sourceHash: scenario.normalizer.sourceHash,
    normalize: (raw) => {
      const index = normalizeCalls++
      if (scenario.normalizer.mode === 'passthrough') return raw
      const entry = scenario.normalizer.table[index]
      expect(entry).toBeDefined()
      expect(isDeepStrictEqual(raw, entry?.raw)).toBe(true)
      return entry?.normalized
    },
  }
  const calculation: CalculationAdapter = {
    execute: (caseId, normalized) => {
      if (!scenario.calculation.supportedCaseIds.includes(caseId)) {
        throw new UnsupportedVectorCase(caseId)
      }
      executedCaseIds.push(caseId)
      const outputs = scenario.calculation.outputs
      return outputs && Object.hasOwn(outputs, caseId)
        ? outputs[caseId]
        : normalized
    },
  }
  const contract: VectorContract = { ...scenario.contract, runner: 'vitest' }

  if (scenario.expected.outcome === 'complete') {
    const report = await runVectors(
      scenario.cases,
      contract,
      normalizer,
      calculation,
    )
    expect(report.complete).toBe(true)
    expect(report.declaredCaseIds).toEqual(scenario.expected.declaredCaseIds)
    expect(report.consumedCaseIds).toEqual(scenario.expected.consumedCaseIds)
  } else {
    let error: unknown
    try {
      await runVectors(scenario.cases, contract, normalizer, calculation)
    } catch (caught) {
      error = caught
    }
    expect(error).toBeInstanceOf(VectorRunError)
    if (!(error instanceof VectorRunError)) {
      throw new Error('ベクタ実行以外の例外が送出された')
    }
    expect(error.message.startsWith(scenario.expected.messagePrefix)).toBe(true)
  }

  expect(normalizeCalls).toBe(scenario.trace.normalizeCalls)
  expect(executedCaseIds).toEqual(scenario.trace.executedCaseIds)
  consumedScenarioIds.add(scenario.id)
})

it('fixture の九シナリオを取りこぼさず消費する', () => {
  const declaredIds = scenarios.map((scenario) => scenario.id)
  expect(scenarios).toHaveLength(9)
  expect(new Set(declaredIds).size).toBe(9)
  expect(consumedScenarioIds.size).toBe(scenarios.length)
  expect([...consumedScenarioIds].sort()).toEqual(
    [...new Set(declaredIds)].sort(),
  )
})

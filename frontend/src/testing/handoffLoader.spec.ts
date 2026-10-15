import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { HandoffLoadError, loadHandoff } from './handoffLoader'

const ROOT = resolve(process.cwd(), '..')
const FIXTURE = 'tests/domain/runners/fixtures/handoff-loader/mutations.json'
type Mutation = Readonly<{
  id: string
  operation:
    | 'directCases'
    | 'unsafeInteger'
    | 'duplicateField'
    | 'negativeZero'
    | 'replace'
    | 'add'
  target: string
  pointer?: string
  value?: unknown
  code: string
}>
const mutations = JSON.parse(
  readFileSync(resolve(ROOT, FIXTURE), 'utf8'),
) as Mutation[]

function source(path: string): unknown {
  return JSON.parse(readFileSync(resolve(ROOT, path), 'utf8')) as unknown
}

function changed(scenario: Mutation): Uint8Array {
  if (scenario.operation === 'directCases') {
    const contract = source(
      'contracts/state-transition/state_transition_contract_v1.json',
    ) as { cases: unknown[] }
    return Buffer.from(JSON.stringify(contract.cases))
  }
  const raw = readFileSync(resolve(ROOT, scenario.target), 'utf8')
  if (
    scenario.operation === 'unsafeInteger' ||
    scenario.operation === 'duplicateField' ||
    scenario.operation === 'negativeZero'
  ) {
    expect(raw).toContain('"schemaVersion": 1')
    const replacement = {
      unsafeInteger: '"schemaVersion": 9007199254740993',
      duplicateField: '"schemaVersion": 1, "schemaVersion": 1',
      negativeZero: '"schemaVersion": -0',
    }[scenario.operation]
    return Buffer.from(raw.replace('"schemaVersion": 1', replacement))
  }
  const document = JSON.parse(raw) as Record<string, unknown>
  const tokens = scenario.pointer?.split('/').slice(1)
  if (!tokens?.length) throw new Error('変異 pointer がない')
  let current: unknown = document
  for (const token of tokens.slice(0, -1)) {
    current = Array.isArray(current)
      ? current[Number(token)]
      : (current as Record<string, unknown>)[token]
  }
  const final = tokens.at(-1)
  if (!final) throw new Error('変異 pointer が空')
  if (Array.isArray(current)) current[Number(final)] = scenario.value
  else (current as Record<string, unknown>)[final] = scenario.value
  return Buffer.from(JSON.stringify(document))
}

it('二契約の全 case を宣言どおりに写像する', () => {
  const loaded = loadHandoff(ROOT)
  for (const [id, path, sourceField] of [
    [
      'state-transition',
      'contracts/state-transition/state_transition_contract_v1.json',
      'expected',
    ],
    [
      'game-end',
      'contracts/state-transition/game_end_contract_v1.json',
      'decision',
    ],
  ] as const) {
    const sourceCases = (source(path) as { cases: Record<string, unknown>[] })
      .cases
    const mapped = loaded.byCalculation[id].cases
    expect(mapped).toHaveLength(sourceCases.length)
    expect(mapped.map((item) => item.caseId)).toEqual(
      sourceCases.map((item) => item.caseId),
    )
    for (const [index, item] of mapped.entries()) {
      expect(Object.keys(item).sort()).toEqual(
        ['caseId', 'raw', 'normalized', 'expected'].sort(),
      )
      expect(item.expected).toEqual(sourceCases[index]?.[sourceField])
      expect(item.raw).toEqual(sourceCases[index]?.raw)
      expect(item.normalized).toEqual(sourceCases[index]?.normalized)
    }
  }
})

it.each(mutations)('$id を $code として拒否する', (scenario) => {
  const bytes = changed(scenario)
  let failure: unknown
  try {
    loadHandoff(ROOT, (path) =>
      path === scenario.target ? bytes : readFileSync(resolve(ROOT, path)),
    )
  } catch (error) {
    failure = error
  }
  expect(failure).toBeInstanceOf(HandoffLoadError)
  expect((failure as HandoffLoadError).code).toBe(scenario.code)
})

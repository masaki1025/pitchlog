import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const vectors = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/batted_hit_prefix_cases_v1.json'),
    'utf8',
  ),
) as {
  cases: { caseId: string; request: unknown; expected: unknown }[]
  rejectionCases: {
    caseId: string
    baseCaseId: string
    replace: { path: string; value: unknown }
    expected: unknown
  }[]
}
const invoke = (request: unknown) =>
  JSON.parse(
    domainOperations.deriveLineupPlayPrefixWithContinuation(
      JSON.stringify(request),
    ),
  )
it('凡打死の明示OUT3-01でv3 sourceを攻守交代へ進め、未確認を拒否する', () => {
  const q = structuredClone(vectors.cases[0]!.request) as {
    t1: Record<string, unknown>
  }
  q.t1.resultId = 'batting-result.batted-out'
  q.t1.thirdOutObservation = 'batter-before-first'
  const result = invoke(q) as {
    ok: boolean
    value?: { t1: Record<string, unknown>; after: Record<string, unknown> }
  }
  expect(result.ok).toBe(true)
  expect(result.value?.t1).toMatchObject({
    batterDestination: { kind: 'out' },
    outEffect: { count: '1', targets: ['batter'] },
  })
  const missing = structuredClone(q)
  missing.t1.thirdOutObservation = 'none'
  expect(invoke(missing)).toStrictEqual({
    ok: false,
    error: { code: 'UNSUPPORTED_T1_SCOPE' },
  })
})
it.each(vectors.cases)('$caseId 既v3の全比較面へ無走者安打を接続する', (c) => {
  expect(invoke(c.request)).toStrictEqual(c.expected)
})
it.each(vectors.rejectionCases)('$caseId 未確認観測を補完しない', (c) => {
  const q = structuredClone(
    vectors.cases.find((x) => x.caseId === c.baseCaseId)!.request,
  ) as { t1: Record<string, unknown> }
  q.t1[c.replace.path.split('/').pop()!] = c.replace.value
  expect(invoke(q)).toStrictEqual(c.expected)
})
it.each([
  'officialScoringPayload',
  'interferenceRuling',
  'runnerAdvanceOverrides',
  'thirdOutObservation',
])('%sの欠落と型違いを新variantの成功へ上げない', (field) => {
  const q = structuredClone(vectors.cases[0]!.request) as {
    t1: Record<string, unknown>
  }
  delete q.t1[field]
  expect(invoke(q)).toStrictEqual({
    ok: false,
    error: { code: 'INVALID_REQUEST' },
  })
  q.t1[field] = false
  expect(invoke(q)).toStrictEqual({
    ok: false,
    error: { code: 'INVALID_REQUEST' },
  })
})
it('旧4fieldへ安打結果だけを差し替えて観測を推測しない', () => {
  const q = structuredClone(vectors.cases[0]!.request) as {
    t1: Record<string, unknown>
  }
  for (const key of [
    'officialScoringPayload',
    'interferenceRuling',
    'runnerAdvanceOverrides',
    'thirdOutObservation',
  ])
    delete q.t1[key]
  expect(invoke(q)).toStrictEqual({
    ok: false,
    error: { code: 'INVALID_REQUEST' },
  })
})
it('余剰・在塁・終了を他の投球結果へfallbackしない', () => {
  const q = structuredClone(vectors.cases[0]!.request) as Record<
    string,
    unknown
  >
  expect(invoke({ ...q, unknown: true })).toStrictEqual({
    ok: false,
    error: { code: 'INVALID_REQUEST' },
  })
  for (const condition of ['state.runners', 'state.gameEnded']) {
    const v = structuredClone(q) as {
      t1: { before: { stateFields: Record<string, unknown> } }
      source: { after: { stateFields: Record<string, unknown> } }
    }
    const value = condition === 'state.runners' ? 'first' : true
    v.t1.before.stateFields[condition] = value
    v.source.after.stateFields[condition] = value
    expect(invoke(v).ok).toBe(false)
  }
})

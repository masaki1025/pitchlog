import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'

const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
    ),
    'utf8',
  ),
)
const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const context = createContext({})
new Script(source).runInContext(context, { timeout: 1000 })
const api = context.PitchlogDomain as {
  deriveState: (request: string) => string
  deriveFirstPitchWithContinuation: (request: string) => string
  deriveOrdinaryPitch: (request: string) => string
}
const invoke = (request: unknown) =>
  JSON.parse(api.deriveOrdinaryPitch(JSON.stringify(request)))

describe('ビルド済み通常投球artifact', () => {
  it('TSをimportせず正式33全値を消費する', () => {
    expect(Object.isFrozen(api)).toBe(true)
    expect(vectors.cases).toHaveLength(33)
    for (const item of vectors.cases)
      expect(invoke(item.request)).toEqual(item.expected)
  })
  it('実artifactのcalled出力だけを次ballへ渡して履歴全体を完全比較する', () => {
    const scenario = vectors.historyTailCases[0]
    const first = vectors.cases.find(
      (item: { caseId: string }) => item.caseId === scenario.firstCaseId,
    )
    const h = invoke(first.request)
    const second = structuredClone(scenario.second.request)
    second.before = h.value.after
    second.history.stack = h.value.historyContext
    expect(invoke(second)).toEqual(scenario.second.expected)
  })
  it.each(['-0', '01', '+1', '1.0'])(
    '履歴内の非canonical %s を実artifactで拒否する',
    (value) => {
      const request = structuredClone(
        vectors.historyTailCases[0].second.request,
      )
      request.history.stack[0].difference.stateFields[
        'state.count.strikes'
      ].after = value
      expect(invoke(request)).toEqual({
        ok: false,
        error: { code: 'INVALID_DECIMAL_INTEGER' },
      })
    },
  )
})

const continuation = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/recording_continuation_scope_v1.json',
    ),
    'utf8',
  ),
)
const foul = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_two_strike_foul_candidate_v1.json',
    ),
    'utf8',
  ),
)
it('再生成した配布物が一般792＋S2foul96と追加4の完全封筒を返す', () => {
  expect(continuation.generalStateCases).toHaveLength(792)
  expect(foul.generalStateCases).toHaveLength(96)
  for (const row of [
    ...continuation.generalStateCases,
    ...foul.generalStateCases,
  ])
    expect(
      invoke({ ...row.event, before: row.before, history: { stack: [] } }),
      row.caseId,
    ).toEqual({ ok: true, value: row.expectedT1 })
  for (const row of foul.cases)
    expect(invoke(row.request), row.caseId).toEqual(row.expected)
})
it('配布物でも旧初球は一般状態を拒否し、ordinaryだけを一般化する', () => {
  const row = continuation.generalStateCases.find(
    (x: {
      event: { resultId: string }
      before: { stateFields: Record<string, unknown> }
    }) =>
      x.event.resultId === 'batting-result.ball' &&
      x.before.stateFields['state.count.balls'] === '0' &&
      x.before.stateFields['state.count.strikes'] === '0',
  )
  const request = { ...row.event, before: row.before }
  expect(JSON.parse(api.deriveState(JSON.stringify(request)))).toEqual({
    ok: false,
    error: { code: 'UNSUPPORTED_T1_SCOPE' },
  })
  expect(
    JSON.parse(
      api.deriveFirstPitchWithContinuation(
        JSON.stringify({
          t1: request,
          rules: {
            regulationInnings: '9',
            coldConditions: [],
            extensionLimit: '9',
            tiebreak: null,
            dh: true,
          },
        }),
      ),
    ).ok,
  ).toBe(false)
})

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

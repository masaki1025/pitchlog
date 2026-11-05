import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import vm from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

type Json = Record<string, unknown>
type Vector = { caseId: string; request: Json; expected: Json }
const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/batted_hit_cases_v1.json',
    ),
    'utf8',
  ),
) as {
  cases: Vector[]
  rejectionCases: Array<{
    caseId: string
    baseCaseId: string
    replace: { path: string; value: unknown }
    expected: Json
  }>
  crossProduct: { nextBattingOrder: Record<string, string> }
}
function object(value: unknown): Json {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    throw new Error('固定手例のobjectがない')
  return value as Json
}
function child(value: unknown, ...path: string[]): Json {
  let result = object(value)
  for (const key of path) result = object(result[key])
  return result
}
const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const context = vm.createContext({})
vm.runInContext(source, context)
window.eval(source)
const callers = {
  source: domainOperations.deriveBattedHit,
  node: (text: string): string =>
    vm.runInContext(
      `PitchlogDomain.deriveBattedHit(${JSON.stringify(text)})`,
      context,
    ) as string,
  browser: (text: string): string =>
    (
      window as unknown as { PitchlogDomain: typeof domainOperations }
    ).PitchlogDomain.deriveBattedHit(text),
}
for (const [name, call] of Object.entries(callers))
  describe(`打球閉ABI ${name}`, () => {
    const invoke = (request: unknown) =>
      JSON.parse(call(JSON.stringify(request)))
    it('実装前に固定した独立16件の全wire値へ一致する', () => {
      for (const row of vectors.cases) {
        const input = structuredClone(row.request)
        expect(invoke(input)).toEqual(row.expected)
        expect(input).toEqual(row.request)
      }
    })
    it('23,328交差でcount/outs/両cursorと全差分の省略を保持する', () => {
      let count = 0
      for (const base of vectors.cases.filter(
        (c) =>
          child(c.request, 'before', 'stateFields')['state.battingOrder'] ===
          '1',
      ))
        for (const outs of ['0', '1', '2'])
          for (const strikes of ['0', '1', '2'])
            for (const balls of ['0', '1', '2', '3'])
              for (const order of ['1', '2', '3', '4', '5', '6', '7', '8', '9'])
                for (const inactive of [
                  '1',
                  '2',
                  '3',
                  '4',
                  '5',
                  '6',
                  '7',
                  '8',
                  '9',
                ]) {
                  const input = structuredClone(base.request),
                    expected = structuredClone(base.expected)
                  const before = child(input, 'before', 'stateFields')
                  const active =
                    before['state.half'] === 'top' ? 'away' : 'home'
                  const other = active === 'away' ? 'home' : 'away'
                  const next = vectors.crossProduct.nextBattingOrder[order]!
                  Object.assign(before, {
                    'state.outs': outs,
                    'state.count.strikes': strikes,
                    'state.count.balls': balls,
                    'state.battingOrder': order,
                  })
                  Object.assign(child(input, 'before', 'battingOrderBySide'), {
                    [active]: order,
                    [other]: inactive,
                  })
                  Object.assign(
                    child(expected, 'value', 'after', 'stateFields'),
                    {
                      'state.outs': outs,
                      'state.battingOrder': next,
                    },
                  )
                  Object.assign(
                    child(expected, 'value', 'after', 'battingOrderBySide'),
                    { [active]: next, [other]: inactive },
                  )
                  const history = child(expected, 'value')
                    .historyContext as unknown[]
                  const diff = child(history[0], 'difference')
                  const states = child(diff, 'stateFields')
                  for (const [key, value] of [
                    ['state.count.strikes', strikes],
                    ['state.count.balls', balls],
                  ]) {
                    if (value === '0') delete states[key!]
                    else states[key!] = { before: value, after: '0' }
                  }
                  states['state.battingOrder'] = { before: order, after: next }
                  diff.battingOrderBySide = {
                    [active]: { before: order, after: next },
                  }
                  expect(invoke(input)).toEqual(expected)
                  count++
                }
      expect(count).toBe(23328)
    }, 60_000)
    it('固定11負例を元の4codeで閉拒否する', () => {
      for (const row of vectors.rejectionCases) {
        const base = vectors.cases.find((c) => c.caseId === row.baseCaseId)!
        const input = structuredClone(base.request)
        const keys = row.replace.path.split('/').filter(Boolean)
        const last = keys.pop()!
        child(input, ...keys)[last] = row.replace.value
        expect(invoke(input)).toEqual(row.expected)
      }
    })
    it('過去tailを全値/順序保持し必須観測を補完しない', () => {
      const base = vectors.cases[0]!
      const tail = child(base.expected, 'value').historyContext as unknown[]
      const input = structuredClone(base.request),
        expected = structuredClone(base.expected)
      child(input, 'history').stack = structuredClone(tail)
      const value = child(expected, 'value')
      value.historyContext = (value.historyContext as unknown[]).concat(
        structuredClone(tail),
      )
      expect(invoke(input)).toEqual(expected)
      for (const key of Object.keys(input)) {
        const missing = structuredClone(input)
        delete missing[key]
        expect(invoke(missing)).toEqual({
          ok: false,
          error: { code: 'INVALID_REQUEST' },
        })
      }
      expect(invoke({ ...input, extra: true })).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
    })
    it('JSON重複/非正準整数/型変換と壊れたJSONを拒否する', () => {
      const base = vectors.cases[0]!
      expect(JSON.parse(call('{'))).toEqual({
        ok: false,
        error: { code: 'INVALID_JSON' },
      })
      const duplicate = JSON.stringify(base.request).replace(
        '{',
        '{"eventKind":"batting-result",',
      )
      expect(JSON.parse(call(duplicate))).toEqual({
        ok: false,
        error: { code: 'INVALID_JSON' },
      })
      for (const value of ['01', '+1', '-0', '-1', '1e2', '1.5']) {
        const input = structuredClone(base.request)
        child(input, 'before', 'scoreboard').hits = value
        expect(invoke(input)).toEqual({
          ok: false,
          error: { code: 'INVALID_DECIMAL_INTEGER' },
        })
      }
      for (const value of [null, false, 12]) {
        const input = structuredClone(base.request)
        child(input, 'before', 'scoreboard').hits = value
        expect(invoke(input)).toEqual({
          ok: false,
          error: { code: 'INVALID_REQUEST' },
        })
      }
    })
    it('huge bigintを正準文字列のまま写し同値count差分を追加しない', () => {
      const base = vectors.cases[0]!,
        input = structuredClone(base.request),
        expected = structuredClone(base.expected)
      const big = '90071992547409931234567890123456789'
      child(input, 'before', 'scoreboard').hits = big
      child(expected, 'value', 'after', 'scoreboard').hits =
        '90071992547409931234567890123456790'
      const history = child(expected, 'value').historyContext as unknown[]
      child(history[0], 'difference', 'scoreboard').hits = {
        before: big,
        after: '90071992547409931234567890123456790',
      }
      expect(invoke(input)).toEqual(expected)
    })
  })

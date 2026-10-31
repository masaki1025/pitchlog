import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import vm from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/terminal_pitch_cases_v1.json',
    ),
    'utf8',
  ),
)
const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const node = vm.createContext({})
vm.runInContext(source, node)
// Vitestの既存jsdom windowで配布物を評価する。
window.eval(source)
const callers = {
  source: domainOperations.deriveTerminalPitch,
  node: (text: string): string =>
    vm.runInContext(
      `PitchlogDomain.deriveTerminalPitch(${JSON.stringify(text)})`,
      node,
    ) as string,
  browser: (text: string): string =>
    (
      window as unknown as { PitchlogDomain: typeof domainOperations }
    ).PitchlogDomain.deriveTerminalPitch(text),
}
for (const [name, call] of Object.entries(callers))
  describe(`無走者BB/HBP ${name}`, () => {
    const invoke = (request: unknown) =>
      JSON.parse(call(JSON.stringify(request)))
    it('15全応答とouts/表裏/打順810交差を規範テンプレートと比較する', () => {
      let count = 0
      for (const item of vectors.cases) {
        expect(invoke(item.request)).toEqual(item.expected)
        for (const outs of vectors.crossProduct.outs)
          for (const half of vectors.crossProduct.half)
            for (const order of vectors.crossProduct.battingOrder) {
              const input = structuredClone(item.request),
                expected = structuredClone(item.expected)
              Object.assign(input.before.stateFields, {
                'state.outs': outs,
                'state.half': half,
                'state.battingOrder': order,
              })
              Object.assign(expected.value.after.stateFields, {
                'state.outs': outs,
                'state.half': half,
                'state.battingOrder':
                  vectors.crossProduct.nextBattingOrder[order],
              })
              expected.value.historyContext[0].difference.stateFields[
                'state.battingOrder'
              ] = {
                before: order,
                after: vectors.crossProduct.nextBattingOrder[order],
              }
              expect(invoke(input)).toEqual(expected)
              count += 1
            }
      }
      expect(count).toBe(810)
    })
    it('規定/延長/TB/巨大整数45状態対と全履歴tailを保持する', () => {
      for (const item of vectors.cases)
        for (const context of vectors.contextPairs) {
          const input = structuredClone(item.request),
            expected = structuredClone(item.expected)
          for (const snapshot of [input.before, expected.value.after]) {
            Object.assign(snapshot.stateFields, {
              'state.inning': context.inning,
              'state.half': context.half,
              'state.tiebreakActive': context.tiebreakActive,
              'state.score': context.score,
            })
            Object.assign(snapshot.scoreboard, {
              inningScores: context.score,
              hits: context.hits,
              errors: context.errors,
              strikeouts: context.strikeouts,
              walks: context.walks,
            })
          }
          if (item.request.resultId === 'batting-result.walk') {
            const walks = (BigInt(context.walks) + 1n).toString()
            expected.value.after.scoreboard.walks = walks
            expected.value.historyContext[0].difference.scoreboard.walks = {
              before: context.walks,
              after: walks,
            }
          }
          const tail = structuredClone(item.expected.value.historyContext[0])
          Object.assign(tail.difference.stateFields, {
            'state.half': { before: 'top', after: 'bottom' },
            'state.runners': { before: 'first-second-third', after: 'empty' },
            'state.inning': { before: '9', after: context.inning },
            'state.score': {
              before: { home: '0', away: '0' },
              after: context.score,
            },
            'state.gameEnded': { before: true, after: false },
            'state.tiebreakActive': { before: false, after: true },
            'state.outs': { before: '2', after: '0' },
          })
          Object.assign(tail.difference.scoreboard, {
            hits: { before: '0', after: context.hits },
            errors: { before: '0', after: context.errors },
            strikeouts: { before: '0', after: context.strikeouts },
            inningScores: {
              before: { home: '0', away: '0' },
              after: context.score,
            },
          })
          input.history.stack = [tail, structuredClone(tail)]
          expected.value.historyContext.push(tail, structuredClone(tail))
          const original = JSON.stringify(input)
          expect(invoke(input)).toEqual(expected)
          expect(JSON.stringify(input)).toBe(original)
          expect(invoke(input)).toEqual(expected)
        }
    })
    it('32拒否とraw3拒否を正確なcodeで返す', () => {
      for (const item of vectors.rejectionCases) {
        const input = structuredClone(
          vectors.cases.find(
            (c: { caseId: string }) => c.caseId === item.baseCaseId,
          ).request,
        )
        let target = input
        for (const key of item.path.slice(0, -1)) target = target[key]
        target[item.path.at(-1)] = item.value
        expect(invoke(input)).toEqual(item.expected)
      }
      for (const item of vectors.rawRejections)
        expect(JSON.parse(call(item.requestJson))).toEqual(item.expected)
    })
    it('履歴旧語彙/不正整数/欠落/余剰/null、投影不一致、escaped重複を拒否する', () => {
      for (const kind of [
        'loaded',
        'negative',
        'missing',
        'extra',
        'null',
        'inning-zero',
      ]) {
        const input = structuredClone(vectors.cases[0].request)
        const tail = structuredClone(
          vectors.cases[0].expected.value.historyContext[0],
        )
        if (kind === 'loaded')
          tail.difference.stateFields['state.runners'].before = 'loaded'
        if (kind === 'negative')
          tail.difference.stateFields['state.count.balls'].before = '-1'
        if (kind === 'missing') delete tail.difference.statFlags.打数
        if (kind === 'extra') tail.difference.extra = 'x'
        if (kind === 'null') tail.difference.scoreboard = null
        if (kind === 'inning-zero')
          tail.difference.stateFields['state.inning'] = {
            before: '0',
            after: '1',
          }
        input.history.stack = [tail]
        expect(invoke(input).ok).toBe(false)
      }
      const input = structuredClone(vectors.cases[0].request)
      input.before.scoreboard.inningScores.home = '1'
      expect(invoke(input)).toEqual({
        ok: false,
        error: { code: 'UNSUPPORTED_T1_SCOPE' },
      })
      const raw = JSON.stringify(input).replace(
        '"hits":"0"',
        '"hits":"0","h\\u0069ts":"0"',
      )
      expect(JSON.parse(call(raw))).toEqual({
        ok: false,
        error: { code: 'INVALID_JSON' },
      })
    })
    it('全23flagsと主要比較面の1箇所変異を完全比較が検出する', () => {
      for (const item of vectors.cases) {
        const actual = invoke(item.request)
        for (const key of Object.keys(item.expected.value.statFlags)) {
          const changed = structuredClone(item.expected)
          changed.value.statFlags[key] = !changed.value.statFlags[key]
          expect(actual).not.toEqual(changed)
        }
        const mutations = [
          (v: typeof actual.value) => {
            v.plateAppearanceEnded = false
          },
          (v: typeof actual.value) => {
            v.batterDestination.base = '2'
          },
          (v: typeof actual.value) => {
            v.after.stateFields['state.count.balls'] = '3'
          },
          (v: typeof actual.value) => {
            v.after.stateFields['state.battingOrder'] = '1'
          },
          (v: typeof actual.value) => {
            v.after.scoreboard.walks = '99'
          },
          (v: typeof actual.value) => {
            v.historyContext = []
          },
          (v: typeof actual.value) => {
            v.countEffect.balls = { kind: 'delta', value: '1' }
          },
        ]
        for (const mutate of mutations) {
          const changed = structuredClone(item.expected)
          mutate(changed.value)
          expect(actual).not.toEqual(changed)
        }
      }
    })
  })

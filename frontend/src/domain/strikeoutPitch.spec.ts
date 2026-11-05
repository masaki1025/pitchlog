import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { isDeepStrictEqual } from 'node:util'
import { createContext, Script } from 'node:vm'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'
import { deriveStrikeout } from './state'
import type { StateFields, Scoreboard } from './stateTypes'

const asset = (name: string) =>
  JSON.parse(
    readFileSync(
      resolve(process.cwd(), '../contracts/state-transition', name),
      'utf8',
    ),
  )
const vectors = asset('strikeout_pitch_cases_v1.json')
const terminal = asset('terminal_pitch_cases_v1.json')
const source = readFileSync(
  resolve(process.cwd(), 'public/domain/pitchlog-domain.js'),
  'utf8',
)
const node = createContext({})
new Script(source).runInContext(node, { timeout: 1000 })
window.eval(source)
const nodeApi = node.PitchlogDomain as typeof domainOperations
const browserApi = (
  window as unknown as { PitchlogDomain: typeof domainOperations }
).PitchlogDomain
const callers = {
  source: domainOperations.deriveStrikeoutPitch,
  nodeArtifact: nodeApi.deriveStrikeoutPitch,
  browserRealmArtifact: browserApi.deriveStrikeoutPitch,
}

/** 受理24手例の非動的効果を保ち、独立軸の規範だけを展開する。 */
function crossing(
  item: (typeof vectors.cases)[number],
  half: string,
  order: string,
  runners: string,
  inactive: string,
) {
  const request = structuredClone(item.request)
  const response = structuredClone(item.expected)
  const before = request.before
  const state = before.stateFields
  const after = response.value.after
  const outgoing = half === 'top' ? 'away' : 'home'
  const incoming = half === 'top' ? 'home' : 'away'
  Object.assign(state, {
    'state.half': half,
    'state.battingOrder': order,
    'state.runners': runners,
  })
  before.battingOrderBySide = { [outgoing]: order, [incoming]: inactive }
  after.battingOrderBySide = {
    [outgoing]: vectors.crossProduct.nextBattingOrder[order],
    [incoming]: inactive,
  }
  Object.assign(after.stateFields, {
    'state.half':
      state['state.outs'] === '2' ? (half === 'top' ? 'bottom' : 'top') : half,
    'state.inning':
      state['state.outs'] === '2' && half === 'bottom' ? '4' : '3',
    'state.runners': state['state.outs'] === '2' ? 'empty' : runners,
    'state.battingOrder':
      state['state.outs'] === '2'
        ? inactive
        : vectors.crossProduct.nextBattingOrder[order],
  })
  for (const runner of ['first', 'second', 'third'])
    response.value.runnerDefaultAdvance[runner] = {
      modality: runners.split('-').includes(runner) ? 'hold' : 'not-applicable',
      destination: null,
    }
  const difference: Record<string, unknown> = {}
  for (const face of ['stateFields', 'scoreboard', 'battingOrderBySide']) {
    const fields: Record<string, unknown> = {}
    for (const key of Object.keys(before[face]))
      if (!isDeepStrictEqual(before[face][key], after[face][key]))
        fields[key] = { before: before[face][key], after: after[face][key] }
    difference[face] = fields
  }
  difference.statFlags = structuredClone(response.value.statFlags)
  response.value.historyContext = [
    { kind: 'confirmed-play', difference },
    ...request.history.stack,
  ]
  return { request, response }
}

for (const [name, call] of Object.entries(callers))
  describe(`正規捕球三振 ${name}`, () => {
    const invoke = (request: unknown) =>
      JSON.parse(call(JSON.stringify(request)))
    it('24全応答と31,104独立cursor交差を規範から全値比較する', () => {
      let count = 0,
        equalScalar = 0
      for (const item of vectors.cases) {
        expect(invoke(item.request)).toEqual(item.expected)
        for (const half of vectors.crossProduct.halves)
          for (const order of vectors.crossProduct.battingOrders)
            for (const runners of vectors.crossProduct.runners)
              for (const inactive of vectors.crossProduct
                .inactiveBattingOrders) {
                const { request, response } = crossing(
                  item,
                  half,
                  order,
                  runners,
                  inactive,
                )
                const actual = invoke(request)
                if (!isDeepStrictEqual(actual, response))
                  expect(actual).toEqual(response)
                if (
                  request.before.stateFields['state.outs'] === '2' &&
                  order === inactive
                ) {
                  equalScalar += 1
                  expect(
                    actual.value.historyContext[0].difference.stateFields,
                  ).not.toHaveProperty('state.battingOrder')
                  expect(
                    actual.value.historyContext[0].difference
                      .battingOrderBySide,
                  ).not.toEqual({})
                }
                count += 1
              }
      }
      expect(count).toBe(31104)
      expect(equalScalar).toBe(1152)
    }, 60000)
    it('90桁の全投影と旧/新履歴tailを順序・全値保持する', () => {
      for (const item of vectors.cases) {
        const { request, response } = crossing(
          item,
          item.request.before.stateFields['state.half'],
          item.request.before.stateFields['state.battingOrder'],
          'first-second-third',
          '8',
        )
        const huge = '9'.repeat(90)
        const tail = [
          structuredClone(terminal.cases[0].expected.value.historyContext[0]),
          structuredClone(item.expected.value.historyContext[0]),
        ]
        request.history.stack = tail
        response.value.historyContext.push(...structuredClone(tail))
        const s = request.before.stateFields,
          a = response.value.after.stateFields
        s['state.inning'] = huge
        a['state.inning'] =
          s['state.outs'] === '2' && s['state.half'] === 'bottom'
            ? (BigInt(huge) + 1n).toString()
            : huge
        s['state.tiebreakActive'] = true
        a['state.tiebreakActive'] = true
        s['state.score'] = { home: huge, away: '9007199254740993' }
        a['state.score'] = structuredClone(s['state.score'])
        for (const board of [
          request.before.scoreboard,
          response.value.after.scoreboard,
        ]) {
          board.inningScores = structuredClone(s['state.score'])
          board.hits = huge
          board.errors = huge
          board.walks = huge
        }
        request.before.scoreboard.strikeouts = huge
        response.value.after.scoreboard.strikeouts = (
          BigInt(huge) + 1n
        ).toString()
        const diff = response.value.historyContext[0].difference
        if (s['state.outs'] === '2' && s['state.half'] === 'bottom')
          diff.stateFields['state.inning'] = {
            before: huge,
            after: a['state.inning'],
          }
        diff.scoreboard.strikeouts = {
          before: huge,
          after: response.value.after.scoreboard.strikeouts,
        }
        const beforeText = JSON.stringify(request)
        expect(invoke(request)).toEqual(response)
        expect(JSON.stringify(request)).toBe(beforeText)
      }
    })
    it('41閉拒否とraw3をコードまで比較し、未対応を成功にしない', () => {
      for (const row of vectors.rejectionCases) {
        const request = structuredClone(
          vectors.cases.find(
            (c: { caseId: string }) => c.caseId === row.baseCaseId,
          ).request,
        )
        let target = request
        for (const key of row.path.slice(0, -1)) target = target[key]
        target[row.path.at(-1)] = row.value
        expect(invoke(request)).toEqual(row.expected)
      }
      for (const row of vectors.rawRejections)
        expect(JSON.parse(call(row.requestJson))).toEqual(row.expected)
      const raw = JSON.stringify(vectors.cases[0].request)
      expect(
        JSON.parse(
          call(raw.replace('"away":"1"', '"away":"1","\\u0061way":"1"')),
        ),
      ).toEqual({ ok: false, error: { code: 'INVALID_JSON' } })
    })
    it('履歴cursorの未知/欠落/不正型・flag数値化を拒否する', () => {
      for (const kind of [
        'cursor-extra',
        'cursor-null',
        'cursor-number',
        'cursor-zero',
        'cursor-missing-pair',
        'flag-number',
        'difference-extra',
      ]) {
        const request = structuredClone(vectors.cases[0].request)
        const entry = structuredClone(
          vectors.cases[0].expected.value.historyContext[0],
        )
        if (kind === 'cursor-extra')
          entry.difference.battingOrderBySide.other = {
            before: '1',
            after: '2',
          }
        if (kind === 'cursor-null') entry.difference.battingOrderBySide = null
        if (kind === 'cursor-number')
          entry.difference.battingOrderBySide.away.before = 1
        if (kind === 'cursor-zero')
          entry.difference.battingOrderBySide.away.before = '0'
        if (kind === 'cursor-missing-pair')
          delete entry.difference.battingOrderBySide.away.after
        if (kind === 'flag-number') entry.difference.statFlags.三振 = 1
        if (kind === 'difference-extra') entry.difference.free = true
        request.history.stack = [entry]
        expect(invoke(request).ok).toBe(false)
      }
    })
  })

it('核はreadonly入力を変えず、返す新cursorも凍結する', () => {
  const before: StateFields = Object.freeze({
    half: 'top',
    strikes: 2n,
    balls: 3n,
    outs: 2n,
    runners: 'loaded',
    battingOrder: 9n,
    tiebreakActive: false,
    gameEnded: false,
    inning: 1n,
    home: 0n,
    away: 0n,
  })
  const board: Scoreboard = Object.freeze({
    home: 0n,
    away: 0n,
    hits: 0n,
    errors: 0n,
    strikeouts: 0n,
    walks: 0n,
  })
  const cursors = Object.freeze({ away: 9n, home: 9n })
  const result = deriveStrikeout(
    before,
    board,
    'batting-result.called-strikeout',
    'pitch-event',
    cursors,
  )
  expect(result?.after.battingOrderBySide).toEqual({ away: 1n, home: 9n })
  expect(result?.after.stateFields.battingOrder).toBe(9n)
  expect(cursors).toEqual({ away: 9n, home: 9n })
  expect(Object.isFrozen(result?.after.battingOrderBySide)).toBe(true)
})

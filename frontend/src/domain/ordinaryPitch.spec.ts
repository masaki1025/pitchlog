import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { domainOperations } from './publicApi'

const vectors = JSON.parse(
  readFileSync(
    resolve(
      process.cwd(),
      '../contracts/state-transition/ordinary_pitch_vectors_v1.json',
    ),
    'utf8',
  ),
)
const invoke = (request: unknown) =>
  JSON.parse(domainOperations.deriveOrdinaryPitch(JSON.stringify(request)))
const request = () => structuredClone(vectors.cases[0].request)

describe('通常33投球の単一TS計算', () => {
  it('正式33全入力の8member・23flag・差分を完全比較する', () => {
    expect(vectors.cases).toHaveLength(33)
    for (const item of vectors.cases)
      expect(invoke(item.request)).toEqual(item.expected)
  })
  it('実called出力を次ballの入力と履歴へ渡し、先頭差分とtailを完全比較する', () => {
    const scenario = vectors.historyTailCases[0]
    const first = vectors.cases.find(
      (item: { caseId: string }) => item.caseId === scenario.firstCaseId,
    )
    const h = invoke(first.request)
    expect(h).toEqual(first.expected)
    const input = structuredClone(scenario.second.request)
    input.before = h.value.after
    input.history.stack = h.value.historyContext
    const original = JSON.stringify(input)
    expect(invoke(input)).toEqual(scenario.second.expected)
    expect(JSON.stringify(input)).toBe(original)
    expect(invoke(input)).toEqual(scenario.second.expected)
  })
  it('tailの全型付き欄・符号付き巨大整数・順序・全flagを保持し切り捨てない', () => {
    const input = request()
    const tail = structuredClone(
      vectors.historyTailCases[0].second.request.history.stack[0],
    )
    tail.difference.stateFields = {
      'state.half': { before: 'top', after: 'bottom' },
      'state.count.strikes': {
        before: '-99999999999999999999999999',
        after: '2',
      },
      'state.count.balls': { before: '0', after: '3' },
      'state.outs': { before: '2', after: '0' },
      'state.runners': { before: 'loaded', after: 'empty' },
      'state.battingOrder': { before: '9', after: '1' },
      'state.tiebreakActive': { before: false, after: true },
      'state.gameEnded': { before: true, after: false },
      'state.inning': { before: '9', after: '10' },
      'state.score': {
        before: { home: '-1', away: '0' },
        after: { home: '2', away: '4' },
      },
    }
    tail.difference.scoreboard = {
      inningScores: {
        before: { home: '0', away: '0' },
        after: { home: '2', away: '4' },
      },
      hits: { before: '0', after: '1' },
    }
    tail.difference.statFlags.打点 = true
    input.history.stack = Array.from({ length: 80 }, (_, index) => ({
      ...structuredClone(tail),
      difference: {
        ...structuredClone(tail.difference),
        statFlags: { ...tail.difference.statFlags, 得点: index % 2 === 0 },
      },
    }))
    const actual = invoke(input)
    expect(actual.ok).toBe(true)
    expect(actual.value.historyContext.slice(1)).toEqual(input.history.stack)
    expect(actual.value.historyContext).toHaveLength(81)
  })
  it.each(['history', 'before', 'resultId'])(
    '必須%sの欠損を成功補完しない',
    (key) => {
      const input = request()
      delete input[key]
      expect(invoke(input)).toEqual({
        ok: false,
        error: { code: 'INVALID_REQUEST' },
      })
    },
  )
  it.each([
    (input: ReturnType<typeof request>) => {
      input.history = {}
    },
    (input: ReturnType<typeof request>) => {
      input.history.stack = null
    },
    (input: ReturnType<typeof request>) => {
      input.history.extra = []
    },
    (input: ReturnType<typeof request>) => {
      input.extra = 'x'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields.extra = '0'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields['state.gameEnded'] = 'false'
    },
    (input: ReturnType<typeof request>) => {
      input.before.scoreboard.inningScores.extra = '0'
    },
  ])('閉じた構造と真理値型を維持する %#', (mutate) => {
    const input = request()
    mutate(input)
    expect(invoke(input)).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
  })
  it.each(['01', '-0', '+1', '1.0', '', 1, null])(
    '非canonical整数%sを拒否する',
    (value) => {
      const input = request()
      input.before.stateFields['state.count.balls'] = value
      expect(invoke(input)).toEqual({
        ok: false,
        error: { code: 'INVALID_DECIMAL_INTEGER' },
      })
    },
  )
  it.each([
    (input: ReturnType<typeof request>) => {
      input.resultId = 'batting-result.home-run'
    },
    (input: ReturnType<typeof request>) => {
      input.eventKind = 'undo'
    },
    (input: ReturnType<typeof request>) => {
      input.pitchEventKind = 'unknown'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields['state.count.strikes'] = '2'
    },
    (input: ReturnType<typeof request>) => {
      input.resultId = 'batting-result.ball'
      input.before.stateFields['state.count.balls'] = '3'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields['state.runners'] = 'unknown'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields['state.inning'] = '0'
    },
    (input: ReturnType<typeof request>) => {
      input.before.scoreboard.hits = '-1'
    },
    (input: ReturnType<typeof request>) => {
      input.before.stateFields['state.outs'] = '3'
    },
  ])('未対応状態・PA終端を成功扱いしない %#', (mutate) => {
    const input = request()
    mutate(input)
    expect(invoke(input)).toEqual({
      ok: false,
      error: { code: 'UNSUPPORTED_T1_SCOPE' },
    })
  })
  it.each([
    (entry: ReturnType<typeof request>) => {
      entry.kind = 'unknown'
    },
    (entry: ReturnType<typeof request>) => {
      entry.difference.stateFields.unknown = { before: '0', after: '1' }
    },
    (entry: ReturnType<typeof request>) => {
      delete entry.difference.statFlags.打点
    },
    (entry: ReturnType<typeof request>) => {
      entry.difference.statFlags.打点 = 1
    },
    (entry: ReturnType<typeof request>) => {
      entry.difference.scoreboard.hits = { before: '0', after: '1', extra: '2' }
    },
  ])('履歴の余剰・欠落・型違反を黙って落とさない %#', (mutate) => {
    const input = request()
    const tail = structuredClone(
      vectors.historyTailCases[0].second.request.history.stack[0],
    )
    mutate(tail)
    input.history.stack = [tail]
    expect(invoke(input)).toEqual({
      ok: false,
      error: { code: 'INVALID_REQUEST' },
    })
  })
  it('旧初球の要求形・成功範囲を広げない', () => {
    expect(
      JSON.parse(domainOperations.deriveState(JSON.stringify(request()))),
    ).toEqual({ ok: false, error: { code: 'INVALID_REQUEST' } })
    const input = request()
    delete input.history
    expect(
      JSON.parse(domainOperations.deriveState(JSON.stringify(input))),
    ).toEqual({ ok: false, error: { code: 'UNSUPPORTED_T1_SCOPE' } })
  })
})

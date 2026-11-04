import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { BattedHitObservation, BattedHitResultId } from './battedHit'
import { deriveBattedHit } from './state'
import type { BattingOrderBySide, Scoreboard, StateFields } from './stateTypes'

// 正本の4結果と到達塁を独立固定。実装のruleを期待生成に使わない。
const CASES = [
  ['batting-result.single', 'reach', 1n, 'first'],
  ['batting-result.double', 'reach', 2n, 'second'],
  ['batting-result.triple', 'reach', 3n, 'third'],
  ['batting-result.home-run', 'score', undefined, 'empty'],
] as const
const NEXT = [2n, 3n, 4n, 5n, 6n, 7n, 8n, 9n, 1n]
const FLAGS = {
  投球回算入アウト: false,
  投球数: true,
  奪三振: false,
  与四球: false,
  与死球: false,
  被安打: true,
  被本塁打: false,
  失点: false,
  失策: false,
  打席: true,
  打数: true,
  安打: true,
  本塁打: false,
  塁打: true,
  犠打: false,
  犠飛: false,
  四球: false,
  死球: false,
  三振: false,
  打撃妨害出塁: false,
  走塁妨害出塁: false,
  得点: false,
  打点: false,
}
function observation(resultId: BattedHitResultId): BattedHitObservation {
  return {
    eventKind: 'batting-result',
    resultId,
    pitchEventKind: 'pitch-event',
    officialScoringPayload: 'no-error',
    interferenceRuling: 'not-required',
    runnerAdvanceOverrides: 'not-applied',
    thirdOutObservation: 'none',
  }
}
function fixture(half: 'top' | 'bottom' = 'top', order = 1n) {
  const before: StateFields = {
    half,
    strikes: 2n,
    balls: 3n,
    outs: 2n,
    runners: 'empty',
    battingOrder: order,
    tiebreakActive: false,
    gameEnded: false,
    inning: 7n,
    home: 3n,
    away: 5n,
  }
  const board: Scoreboard = {
    home: 3n,
    away: 5n,
    hits: 12n,
    errors: 2n,
    strikeouts: 4n,
    walks: 3n,
  }
  const cursors: BattingOrderBySide =
    half === 'top' ? { away: order, home: 6n } : { away: 6n, home: order }
  return { before, board, cursors }
}
function expected(f: ReturnType<typeof fixture>, item: (typeof CASES)[number]) {
  const [result, kind, base, runners] = item
  const hr = result === 'batting-result.home-run'
  const home = f.before.home + (hr && f.before.half === 'bottom' ? 1n : 0n)
  const away = f.before.away + (hr && f.before.half === 'top' ? 1n : 0n)
  const order = NEXT[Number(f.before.battingOrder - 1n)]!
  return {
    countEffect: {
      strikes: { kind: 'reset', value: 0n },
      balls: { kind: 'reset', value: 0n },
    },
    plateAppearanceEnded: true,
    batterDestination: base === undefined ? { kind } : { kind, base },
    runnerDefaultAdvance: {
      first: { modality: 'not-applicable', destination: null },
      second: { modality: 'not-applicable', destination: null },
      third: { modality: 'not-applicable', destination: null },
    },
    outEffect: { count: 0n, targets: [] },
    statFlags: {
      ...FLAGS,
      被本塁打: hr,
      本塁打: hr,
      失点: hr,
      得点: hr,
      打点: hr,
    },
    history: {
      ballsBefore: f.before.balls,
      ballsAfter: 0n,
      strikesBefore: f.before.strikes,
      strikesAfter: 0n,
    },
    after: {
      stateFields: {
        ...f.before,
        strikes: 0n,
        balls: 0n,
        runners,
        battingOrder: order,
        home,
        away,
      },
      scoreboard: { ...f.board, home, away, hits: f.board.hits + 1n },
      battingOrderBySide:
        f.before.half === 'top'
          ? { away: order, home: f.cursors.home }
          : { away: f.cursors.away, home: order },
    },
  }
}
function calculate(f: ReturnType<typeof fixture>, input: unknown) {
  return deriveBattedHit(
    f.before,
    f.board,
    input as BattedHitObservation,
    f.cursors,
  )
}

describe('無走者4安打の唯一前進核', () => {
  it('独立16手例の全値を比較し、二死でも交代せず打順9を1へ戻す', () => {
    for (const half of ['top', 'bottom'] as const)
      for (const order of [1n, 9n])
        for (const item of CASES) {
          const f = fixture(half, order),
            original = structuredClone(f)
          expect(calculate(f, observation(item[0]))).toEqual(expected(f, item))
          expect(f).toEqual(original)
        }
  })
  it('outs/count/両half/独立両cursorの23,328交差で全応答を比較する', () => {
    let count = 0
    for (const item of CASES)
      for (const half of ['top', 'bottom'] as const)
        for (let outs = 0n; outs <= 2n; outs++)
          for (let strikes = 0n; strikes <= 2n; strikes++)
            for (let balls = 0n; balls <= 3n; balls++)
              for (let order = 1n; order <= 9n; order++)
                for (let inactive = 1n; inactive <= 9n; inactive++) {
                  const f = fixture(half, order)
                  Object.assign(f.before, { outs, strikes, balls })
                  if (half === 'top') f.cursors.home = inactive
                  else f.cursors.away = inactive
                  expect(calculate(f, observation(item[0]))).toEqual(
                    expected(f, item),
                  )
                  count++
                }
    expect(count).toBe(23328)
  }, 30_000)
  it('巨大整数の状態/得点/board/履歴を丸めず入力を保持する', () => {
    const big = 90071992547409931234567890123456789n
    for (const half of ['top', 'bottom'] as const)
      for (const item of CASES) {
        const f = fixture(half, 9n)
        Object.assign(f.before, { inning: big, home: big, away: big + 2n })
        Object.assign(f.board, {
          home: big,
          away: big + 2n,
          hits: big,
          errors: big,
          strikeouts: big,
          walks: big,
        })
        const original = structuredClone(f)
        expect(calculate(f, observation(item[0]))).toEqual(expected(f, item))
        expect(f).toEqual(original)
      }
  })
  it('既正式3安打代表とHRの23flagに一致し未知flagを足さない', () => {
    const contract = JSON.parse(
      readFileSync(
        resolve(
          process.cwd(),
          '../contracts/state-transition/state_transition_contract_v1.json',
        ),
        'utf8',
      ),
    ) as {
      matrixRows: Array<{
        resultId: string
        statFlags: Record<string, boolean>
      }>
    }
    for (const item of CASES) {
      const actual = calculate(fixture(), observation(item[0]))!
      const row = contract.matrixRows.find((r) => r.resultId === item[0])!
      expect(actual.statFlags).toEqual(row.statFlags)
      expect(Object.keys(actual.statFlags)).toHaveLength(23)
      expect(Object.values(actual.statFlags).filter(Boolean)).toHaveLength(
        item[0] === 'batting-result.home-run' ? 11 : 6,
      )
    }
  })
  it('全観測fieldの欠落/未確認/矛盾と未知fieldを拒否する', () => {
    const valid = observation('batting-result.single')
    for (const key of Object.keys(valid)) {
      const missing: Record<string, unknown> = { ...valid }
      delete missing[key]
      expect(calculate(fixture(), missing)).toBeNull()
      for (const value of [null, undefined, false, 'unconfirmed'])
        expect(calculate(fixture(), { ...valid, [key]: value })).toBeNull()
    }
    for (const value of [
      null,
      [],
      'single',
      { ...valid, extra: true },
      { ...valid, resultId: 'batting-result.walk' },
      { ...valid, officialScoringPayload: 'single-error' },
      { ...valid, interferenceRuling: 'batting:penalty-award' },
      { ...valid, runnerAdvanceOverrides: 'single-runner-out' },
      { ...valid, thirdOutObservation: 'other-third-out' },
      { ...valid, pitchEventKind: 'non-pitch-event' },
      { ...valid, [Symbol('hidden')]: true },
    ])
      expect(calculate(fixture(), value)).toBeNull()
  })
  it('観測getterを実行せず拒否し数値型の暗黙変換を許さない', () => {
    let calls = 0
    const input = { ...observation('batting-result.single') }
    Object.defineProperty(input, 'resultId', {
      get: () => {
        calls++
        return 'batting-result.home-run'
      },
    })
    expect(calculate(fixture(), input)).toBeNull()
    expect(calls).toBe(0)
    for (const target of ['before', 'board', 'cursors'] as const)
      for (const [key, value] of Object.entries(fixture()[target])) {
        if (typeof value !== 'bigint') continue
        for (const replacement of [
          Number(value),
          value.toString(),
          null,
          true,
        ]) {
          const f = fixture()
          Object.assign(f[target], { [key]: replacement })
          expect(calculate(f, observation('batting-result.single'))).toBeNull()
        }
      }
  })
  it('在塁/終了/TB/負値/範囲外/boardとcursorの不整合を拒否する', () => {
    for (const runners of [
      'first',
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
      'unknown',
    ]) {
      const f = fixture()
      Object.assign(f.before, { runners })
      expect(calculate(f, observation('batting-result.single'))).toBeNull()
    }
    for (const [key, value] of [
      ['gameEnded', true],
      ['tiebreakActive', true],
      ['half', 'unknown'],
      ['inning', 0n],
      ['outs', -1n],
      ['outs', 3n],
      ['strikes', -1n],
      ['strikes', 3n],
      ['balls', -1n],
      ['balls', 4n],
      ['battingOrder', 0n],
      ['battingOrder', 10n],
      ['home', -1n],
      ['away', -1n],
      ['home', 4n],
      ['away', 6n],
    ] as const) {
      const f = fixture()
      Object.assign(f.before, { [key]: value })
      expect(calculate(f, observation('batting-result.single'))).toBeNull()
    }
    for (const key of [
      'home',
      'away',
      'hits',
      'errors',
      'strikeouts',
      'walks',
    ]) {
      const f = fixture()
      Object.assign(f.board, { [key]: -1n })
      expect(calculate(f, observation('batting-result.single'))).toBeNull()
    }
    for (const half of ['top', 'bottom'] as const)
      for (const cursors of [
        { away: 0n, home: 6n },
        { away: 10n, home: 6n },
        { away: 1n, home: 0n },
        { away: 1n, home: 10n },
        { away: 2n, home: 2n },
      ]) {
        const f = fixture(half)
        f.cursors = cursors
        expect(calculate(f, observation('batting-result.home-run'))).toBeNull()
      }
  })
  it('call間でflags/after/cursorを共有せずT2成功を仮定しない', () => {
    const f = fixture('bottom', 9n)
    const first = calculate(f, observation('batting-result.home-run'))!
    first.statFlags.安打 = false
    first.after.stateFields.home = 0n
    expect(calculate(f, observation('batting-result.home-run'))).toEqual(
      expected(f, CASES[3]),
    )
    expect(first.after.stateFields.gameEnded).toBe(false)
    expect(Object.keys(first)).not.toContain('t2')
  })
})

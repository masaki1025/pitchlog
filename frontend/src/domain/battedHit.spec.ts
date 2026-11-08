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

describe('凡打死の正本有限入力', () => {
  it('一塁走者の実封殺と打者を併殺の2アウトへ結び、別IDや推測入力を拒否する', () => {
    const f = fixture('top', 1n)
    f.before.outs = 0n
    f.before.runners = 'first'
    const input = {
      ...observation('batting-result.double-play'),
      outRunner: {
        base: '1' as const,
        runnerId: '10000000-0000-0000-0000-000000000065',
        outKind: 'force-out' as const,
      },
    }
    const row = calculate(f, input)!
    expect(row.outEffect).toEqual({
      count: 2n,
      targets: [{ kind: 'batter' }, { kind: 'runner', base: 1n }],
    })
    expect(row.after.stateFields).toMatchObject({
      outs: 2n,
      runners: 'empty',
      half: 'top',
    })
    expect(row.statFlags).toMatchObject({ 打席: true, 打数: true, 安打: false })
    expect(calculate(f, { ...input, outRunner: undefined })).toBeNull()
    expect(
      calculate(f, { ...input, outRunner: { ...input.outRunner, base: '2' } }),
    ).toBeNull()
    expect(
      calculate(f, {
        ...input,
        outRunner: { ...input.outRunner, outKind: 'tag-out' },
      }),
    ).toBeNull()
    f.before.outs = 1n
    expect(calculate(f, input)).toBeNull()
  })
  it('無走者0アウトは打者1アウト・打数1、2アウトは明示OUT3-01で攻守交代する', () => {
    const contract = JSON.parse(
      readFileSync(
        resolve(
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
    const flags = contract.matrixRows.find(
      (r) => r.resultId === 'batting-result.batted-out',
    )!.statFlags
    const first = fixture('top', 1n)
    first.before.outs = 0n
    const one = calculate(first, observation('batting-result.batted-out'))!
    expect(one.outEffect).toEqual({ count: 1n, targets: [{ kind: 'batter' }] })
    expect(one.batterDestination).toEqual({ kind: 'out' })
    expect(one.statFlags).toEqual(flags)
    expect(one.after.stateFields).toMatchObject({
      outs: 1n,
      half: 'top',
      runners: 'empty',
      battingOrder: 2n,
    })
    const last = fixture('top', 1n)
    const beforeFirst = {
      ...observation('batting-result.batted-out'),
      thirdOutObservation: 'batter-before-first' as const,
    }
    const three = calculate(last, beforeFirst)!
    expect(three.outEffect).toEqual({
      count: 1n,
      targets: [{ kind: 'batter' }],
    })
    expect(three.statFlags).toEqual(flags)
    expect(three.after.stateFields).toMatchObject({
      outs: 0n,
      half: 'bottom',
      runners: 'empty',
      battingOrder: 6n,
    })
    expect(calculate(last, observation('batting-result.batted-out'))).toBeNull()
    expect(calculate(first, beforeFirst)).toBeNull()
    const withRunner = fixture('top', 1n)
    withRunner.before.outs = 0n
    withRunner.before.runners = 'first'
    expect(
      calculate(withRunner, observation('batting-result.batted-out')),
    ).toBeNull()
  })
  it('三塁走者の実生還は通常アウトで有効、打者の一塁前第3アウトでは無効', () => {
    const move = {
      ...observation('batting-result.batted-out'),
      runnerAdvanceOverrides: {
        kind: 'applied' as const,
        overrides: [{ runnerBase: '3' as const, destination: '4' as const }],
      },
    }
    const one = fixture('top')
    one.before.outs = 0n
    one.before.runners = 'third'
    const scored = calculate(one, move)!
    expect(scored.outEffect).toEqual({
      count: 1n,
      targets: [{ kind: 'batter' }],
    })
    expect(scored.after.stateFields).toMatchObject({
      outs: 1n,
      away: 6n,
      runners: 'empty',
    })
    expect(scored.statFlags).toMatchObject({
      得点: true,
      失点: true,
      打点: true,
    })
    expect(scored.runnerScoreEffects).toEqual([
      { base: 3n, validRun: true, rbiCredited: true },
    ])
    const restarted = calculate(one, {
      ...move,
      rbiRulingByRunner: { '3': 'stopped-and-restarted' },
    })!
    expect(restarted.after.stateFields.away).toBe(6n)
    expect(restarted.statFlags.打点).toBe(false)
    expect(restarted.runnerScoreEffects).toEqual([
      { base: 3n, validRun: true, rbiCredited: false },
    ])
    for (const cause of ['ordinary-play', 'kept-running']) {
      expect(
        calculate(one, { ...move, rbiRulingByRunner: { '3': cause } })!
          .statFlags.打点,
      ).toBe(true)
    }
    expect(
      calculate(one, { ...move, rbiRulingByRunner: { '1': 'ordinary-play' } }),
    ).toBeNull()
    expect(calculate(one, { ...move, rbiRulingByRunner: {} })).toBeNull()
    expect(
      calculate(one, { ...move, rbiRulingByRunner: { '3': 'unknown' } }),
    ).toBeNull()
    const last = fixture('top')
    last.before.runners = 'third'
    const noRun = calculate(last, {
      ...move,
      thirdOutObservation: 'batter-before-first',
    })!
    expect(noRun.after.stateFields).toMatchObject({
      half: 'bottom',
      away: 5n,
      runners: 'empty',
    })
    expect(noRun.statFlags).toMatchObject({
      得点: false,
      失点: false,
      打点: false,
    })
    expect(noRun.runnerScoreEffects).toEqual([
      { base: 3n, validRun: false, rbiCredited: false },
    ])
    expect(calculate(last, move)).toBeNull()
    expect(
      calculate(one, { ...move, runnerAdvanceOverrides: 'not-applied' }),
    ).toBeNull()
  })
})

describe('既正本の野選・犠打・犠飛有限行', () => {
  const matrix = JSON.parse(
    readFileSync(
      resolve(
        '../contracts/state-transition/state_transition_contract_v1.json',
      ),
      'utf8',
    ),
  ) as {
    matrixRows: Array<{ resultId: string; statFlags: Record<string, boolean> }>
  }
  const forced = {
    kind: 'applied' as const,
    overrides: [
      { runnerBase: '1' as const, destination: '2' as const },
      { runnerBase: '2' as const, destination: '3' as const },
    ],
  }
  it.each([
    ['batting-result.batted-reach', 'reach', 0n, 'loaded'],
    ['batting-result.fielders-choice', 'reach', 0n, 'loaded'],
    ['batting-result.sacrifice-bunt', 'out', 1n, 'second-third'],
  ] as const)(
    '%sの既matrix行と全23flag・到達/アウトが一致',
    (resultId, batter, outs, runners) => {
      const f = fixture('top')
      f.before.outs = 0n
      f.before.runners = 'first-second'
      const result = calculate(f, {
        ...observation(resultId),
        runnerAdvanceOverrides: forced,
      })!
      expect(result.batterDestination.kind).toBe(batter)
      expect(result.outEffect.count).toBe(outs)
      expect(result.after.stateFields).toMatchObject({ runners, outs })
      expect(result.statFlags).toEqual(
        matrix.matrixRows.find((row) => row.resultId === resultId)!.statFlags,
      )
    },
  )
  it('一三塁へ拡張せず三塁走者の犠飛1行だけ得点/打点/犠飛を算入', () => {
    const f = fixture('top')
    f.before.outs = 0n
    f.before.runners = 'third'
    const result = calculate(f, {
      ...observation('batting-result.sacrifice-fly'),
      runnerAdvanceOverrides: {
        kind: 'applied',
        overrides: [{ runnerBase: '3', destination: '4' }],
      },
    })!
    expect(result.after.stateFields).toMatchObject({
      outs: 1n,
      runners: 'empty',
      away: 6n,
    })
    expect(result.statFlags).toEqual(
      matrix.matrixRows.find(
        (row) => row.resultId === 'batting-result.sacrifice-fly',
      )!.statFlags,
    )
    const invalid = fixture('top')
    invalid.before.runners = 'first-third'
    expect(
      calculate(invalid, {
        ...observation('batting-result.sacrifice-fly'),
        runnerAdvanceOverrides: {
          kind: 'applied',
          overrides: [{ runnerBase: '3', destination: '4' }],
        },
      }),
    ).toBeNull()
  })
})

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

describe('走者あり打球の明示進塁だけを接続する', () => {
  function runnerFixture() {
    const before: StateFields = {
      half: 'top',
      strikes: 1n,
      balls: 2n,
      outs: 0n,
      runners: 'first',
      battingOrder: 2n,
      tiebreakActive: false,
      gameEnded: false,
      inning: 1n,
      home: 0n,
      away: 0n,
    }
    const board: Scoreboard = {
      home: 0n,
      away: 0n,
      hits: 1n,
      errors: 0n,
      strikeouts: 0n,
      walks: 0n,
    }
    return { before, board, cursors: { away: 2n, home: 1n } }
  }
  function runnerObservation(
    resultId: BattedHitResultId,
    destination: '2' | '3' | '4',
  ): BattedHitObservation {
    return {
      ...observation(resultId),
      runnerAdvanceOverrides: {
        kind: 'applied',
        overrides: [{ runnerBase: '1', destination }],
      },
    }
  }
  it('単打で一塁走者を三塁へ明示し、打者一塁・得点0を返す', () => {
    const f = runnerFixture()
    expect(
      deriveBattedHit(
        f.before,
        f.board,
        runnerObservation('batting-result.single', '3'),
        f.cursors,
      ),
    ).toEqual({
      countEffect: {
        strikes: { kind: 'reset', value: 0n },
        balls: { kind: 'reset', value: 0n },
      },
      plateAppearanceEnded: true,
      batterDestination: { kind: 'reach', base: 1n },
      runnerDefaultAdvance: {
        first: { modality: 'forced', destination: 3n },
        second: { modality: 'not-applicable', destination: null },
        third: { modality: 'not-applicable', destination: null },
      },
      outEffect: { count: 0n, targets: [] },
      statFlags: { ...FLAGS },
      history: {
        ballsBefore: 2n,
        ballsAfter: 0n,
        strikesBefore: 1n,
        strikesAfter: 0n,
      },
      after: {
        stateFields: {
          ...f.before,
          strikes: 0n,
          balls: 0n,
          runners: 'first-third',
          battingOrder: 3n,
        },
        scoreboard: { ...f.board, hits: 2n },
        battingOrderBySide: { away: 3n, home: 1n },
      },
    })
  })
  it('二塁打で一塁走者の生還を明示し、得点1・RBI-08の打点1を返す', () => {
    const f = runnerFixture()
    expect(
      deriveBattedHit(
        f.before,
        f.board,
        runnerObservation('batting-result.double', '4'),
        f.cursors,
      ),
    ).toEqual({
      countEffect: {
        strikes: { kind: 'reset', value: 0n },
        balls: { kind: 'reset', value: 0n },
      },
      plateAppearanceEnded: true,
      batterDestination: { kind: 'reach', base: 2n },
      runnerDefaultAdvance: {
        first: { modality: 'forced', destination: 4n },
        second: { modality: 'not-applicable', destination: null },
        third: { modality: 'not-applicable', destination: null },
      },
      outEffect: { count: 0n, targets: [] },
      statFlags: { ...FLAGS, 得点: true, 失点: true, 打点: true },
      history: {
        ballsBefore: 2n,
        ballsAfter: 0n,
        strikesBefore: 1n,
        strikesAfter: 0n,
      },
      after: {
        stateFields: {
          ...f.before,
          strikes: 0n,
          balls: 0n,
          runners: 'second',
          battingOrder: 3n,
          away: 1n,
        },
        scoreboard: { ...f.board, away: 1n, hits: 2n },
        battingOrderBySide: { away: 3n, home: 1n },
      },
    })
  })
  it('未確認・後退・不在塁・重複・打者との塁衝突を拒否する', () => {
    const f = runnerFixture()
    const single = observation('batting-result.single')
    expect(deriveBattedHit(f.before, f.board, single, f.cursors)).toBeNull()
    for (const overrides of [
      [],
      [{ runnerBase: '1', destination: '1' }],
      [{ runnerBase: '2', destination: '3' }],
      [
        { runnerBase: '1', destination: '3' },
        { runnerBase: '1', destination: '2' },
      ],
    ]) {
      expect(
        deriveBattedHit(
          f.before,
          f.board,
          {
            ...single,
            runnerAdvanceOverrides: { kind: 'applied', overrides },
          } as BattedHitObservation,
          f.cursors,
        ),
      ).toBeNull()
    }
    // 不在塁の指定やフォース連鎖の指定不足は成功にしない。
    for (const runners of [
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
    ] as const) {
      const before = { ...f.before, runners }
      const overrides = [{ runnerBase: '1', destination: '3' }]
      expect(
        deriveBattedHit(
          before,
          f.board,
          {
            ...single,
            runnerAdvanceOverrides: { kind: 'applied', overrides },
          } as BattedHitObservation,
          f.cursors,
        ),
      ).toBeNull()
    }
    // 本塁打で一人でも塁上に残す観測はRBI-06の前提に反する。
    expect(
      deriveBattedHit(
        f.before,
        f.board,
        runnerObservation('batting-result.home-run', '3'),
        f.cursors,
      ),
    ).toBeNull()
    // 二塁打で一塁走者を二塁に止めると打者と衝突する。
    expect(
      deriveBattedHit(
        f.before,
        f.board,
        runnerObservation('batting-result.double', '2'),
        f.cursors,
      ),
    ).toBeNull()
  })
  it('overrideのgetter/余剰field/未知kindを実行せず拒否する', () => {
    const f = runnerFixture()
    let calls = 0
    const overrides: Record<string, unknown> = {
      kind: 'applied',
      overrides: [{ runnerBase: '1', destination: '3' }],
    }
    Object.defineProperty(overrides, 'kind', {
      get: () => {
        calls++
        return 'applied'
      },
    })
    expect(
      deriveBattedHit(
        f.before,
        f.board,
        {
          ...observation('batting-result.single'),
          runnerAdvanceOverrides: overrides,
        } as unknown as BattedHitObservation,
        f.cursors,
      ),
    ).toBeNull()
    expect(calls).toBe(0)
    for (const value of [
      { kind: 'unknown', overrides: [] },
      { kind: 'applied', overrides: [], extra: true },
      {
        kind: 'applied',
        overrides: [{ runnerBase: '1', destination: '3', extra: true }],
      },
    ])
      expect(
        deriveBattedHit(
          f.before,
          f.board,
          {
            ...observation('batting-result.single'),
            runnerAdvanceOverrides: value,
          } as unknown as BattedHitObservation,
          f.cursors,
        ),
      ).toBeNull()
  })
  it('一二塁の単打で両フォース走者の実進塁を反映し、生還1をRBI-08で計上する', () => {
    const f = runnerFixture()
    f.before.runners = 'first-second'
    const result = deriveBattedHit(
      f.before,
      f.board,
      {
        ...observation('batting-result.single'),
        runnerAdvanceOverrides: {
          kind: 'applied',
          overrides: [
            { runnerBase: '1', destination: '3' },
            { runnerBase: '2', destination: '4' },
          ],
        },
      },
      f.cursors,
    )
    expect(result?.runnerDefaultAdvance).toEqual({
      first: { modality: 'forced', destination: 3n },
      second: { modality: 'forced', destination: 4n },
      third: { modality: 'not-applicable', destination: null },
    })
    expect(result?.after.stateFields.runners).toBe('first-third')
    expect(result?.after.stateFields.away).toBe(1n)
    expect(result?.statFlags).toEqual({
      ...FLAGS,
      得点: true,
      失点: true,
      打点: true,
    })
  })
  it('満塁本塁打は全走者の明示生還と打者の生還を合わせて4点とする', () => {
    const f = runnerFixture()
    f.before.runners = 'loaded'
    const result = deriveBattedHit(
      f.before,
      f.board,
      {
        ...observation('batting-result.home-run'),
        runnerAdvanceOverrides: {
          kind: 'applied',
          overrides: [
            { runnerBase: '1', destination: '4' },
            { runnerBase: '2', destination: '4' },
            { runnerBase: '3', destination: '4' },
          ],
        },
      },
      f.cursors,
    )
    expect(result?.runnerDefaultAdvance).toEqual({
      first: { modality: 'optional', destination: 4n },
      second: { modality: 'optional', destination: 4n },
      third: { modality: 'optional', destination: 4n },
    })
    expect(result?.after.stateFields.runners).toBe('empty')
    expect(result?.after.stateFields.away).toBe(4n)
    expect(result?.after.scoreboard.away).toBe(4n)
    expect(result?.statFlags).toEqual({
      ...FLAGS,
      被本塁打: true,
      本塁打: true,
      得点: true,
      失点: true,
      打点: true,
    })
  })
})

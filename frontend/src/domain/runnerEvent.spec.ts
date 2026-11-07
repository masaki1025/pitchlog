import { describe, expect, it } from 'vitest'
import { deriveRunnerOperation } from './state'
import type { StateFields, Scoreboard } from './stateTypes'
import type { RunnerRuleRequest } from './runnerEvent'
import { bindRunnerOutcomes, type LiveRunnerIdentity } from './runnerEvent'

const first = '10000000-0000-0000-0000-000000000001'
const second = '10000000-0000-0000-0000-000000000002'
const oldPitcher = '10000000-0000-0000-0000-000000000011'
const newPitcher = '10000000-0000-0000-0000-000000000012'
const live: Array<LiveRunnerIdentity> = [
  { base: '1', runnerId: first, responsiblePitcherId: oldPitcher },
  { base: '2', runnerId: second, responsiblePitcherId: newPitcher },
]
function observed() {
  return {
    first: {
      kind: 'out',
      runner: { kind: 'official', player_id: first },
      attempted_base: 'second',
      out_kind: 'caught-stealing',
    },
    second: {
      kind: 'safe-advance',
      runner: { kind: 'official', player_id: second },
      destination: 'home',
    },
  }
}

describe('正式走者結果と同sourceのID束縛', () => {
  it('out/実到達/前任責任をそのまま保持し、元入力を変えない', () => {
    const input = observed()
    const original = structuredClone(input)
    const result = bindRunnerOutcomes(input, 'first-second', live)
    expect(result).toEqual([
      {
        slot: 'first',
        base: 1n,
        runnerId: first,
        responsiblePitcherId: oldPitcher,
        outcome: input.first,
      },
      {
        slot: 'second',
        base: 2n,
        runnerId: second,
        responsiblePitcherId: newPitcher,
        outcome: input.second,
      },
    ])
    expect(input).toEqual(original)
    expect(Object.isFrozen(result)).toBe(true)
    expect(Object.isFrozen(result?.[0])).toBe(true)
  })
  it('明示holdを停止として保持する', () => {
    const input = {
      first: { kind: 'hold', runner: { kind: 'official', player_id: first } },
    }
    expect(
      bindRunnerOutcomes(input, 'first', live.slice(0, 1))?.[0]?.outcome,
    ).toEqual(input.first)
  })
  it.each([
    ['空の対象', () => ({})],
    ['不在塁', () => ({ ...observed(), third: observed().first })],
    [
      '別走者',
      () => ({
        ...observed(),
        first: {
          ...observed().first,
          runner: { kind: 'official', player_id: second },
        },
      }),
    ],
    [
      'temporary未解決',
      () => ({
        ...observed(),
        first: {
          ...observed().first,
          runner: { kind: 'temporary', temporary_id: first },
        },
      }),
    ],
    [
      'out原因不足',
      () => ({
        ...observed(),
        first: {
          kind: 'out',
          runner: observed().first.runner,
          attempted_base: 'second',
        },
      }),
    ],
    [
      '企図塁不足',
      () => ({
        ...observed(),
        first: {
          kind: 'out',
          runner: observed().first.runner,
          out_kind: 'caught-stealing',
        },
      }),
    ],
    [
      '未知原因',
      () => ({
        ...observed(),
        first: { ...observed().first, out_kind: 'unknown' },
      }),
    ],
    [
      '未知到達',
      () => ({
        ...observed(),
        second: { ...observed().second, destination: '5' },
      }),
    ],
    [
      '余剰',
      () => ({
        ...observed(),
        first: { ...observed().first, valid_run: true },
      }),
    ],
  ])('%sを現在値/既定値で補完しない', (_, input) => {
    expect(bindRunnerOutcomes(input(), 'first-second', live)).toBeNull()
  })
  it('正式partial mapの未対象を観測済holdへ補完しない', () => {
    const result = bindRunnerOutcomes(
      { first: observed().first },
      'first-second',
      live,
    )
    expect(result).toHaveLength(1)
    expect(result?.[0]?.slot).toBe('first')
  })
  it('getterを評価しない', () => {
    let accessed = false
    const value = observed()
    Object.defineProperty(value, 'first', {
      get() {
        accessed = true
        return {}
      },
    })
    expect(bindRunnerOutcomes(value, 'first-second', live)).toBeNull()
    expect(accessed).toBe(false)
  })
  it('sourceの重複/不足責任/状態不一致を拒否する', () => {
    for (const source of [
      [live[0]!, live[0]!],
      [{ ...live[0]!, responsiblePitcherId: '' }, live[1]!],
      [{ ...live[0]!, runnerId: second }, live[1]!],
      [live[0]!],
    ])
      expect(bindRunnerOutcomes(observed(), 'first-second', source)).toBeNull()
    expect(bindRunnerOutcomes(observed(), 'first', live)).toBeNull()
    expect(bindRunnerOutcomes({}, 'empty', [])).toBeNull()
  })
})

const third = '10000000-0000-0000-0000-000000000003'
const cursors = { away: 3n, home: 5n }
function context(runners: StateFields['runners'] = 'first-second') {
  const before: StateFields = {
    half: 'top',
    inning: 1n,
    outs: 0n,
    strikes: 1n,
    balls: 1n,
    runners,
    battingOrder: 3n,
    tiebreakActive: false,
    gameEnded: false,
    home: 0n,
    away: 0n,
  }
  const board: Scoreboard = {
    home: 0n,
    away: 0n,
    hits: 2n,
    errors: 0n,
    strikeouts: 0n,
    walks: 0n,
  }
  return { before, board }
}
function ref(id: string) {
  return { kind: 'official', player_id: id }
}
function request(
  overrides: Partial<RunnerRuleRequest> = {},
): RunnerRuleRequest {
  return {
    eventKind: 'runner-event',
    operationId: 'strategy-category.steal',
    pitchEventKind: 'non-pitch-event',
    primaryResultId: null,
    byRunner: {
      first: {
        kind: 'safe-advance',
        runner: ref(first),
        destination: 'second',
      },
    },
    thirdOutObservation: { kind: 'not-required' },
    thirdOutTimingByRunner: {},
    ...overrides,
  }
}
const loadedLive: Array<LiveRunnerIdentity> = [
  ...live,
  { base: '3', runnerId: third, responsiblePitcherId: oldPitcher },
]
function allAdvance() {
  return {
    first: { kind: 'safe-advance', runner: ref(first), destination: 'second' },
    second: { kind: 'safe-advance', runner: ref(second), destination: 'third' },
    third: { kind: 'safe-advance', runner: ref(third), destination: 'home' },
  }
}

describe('共通Ruleによる走者操作', () => {
  it('SBを伴う通常球は既カウントを一度だけ加算し、打席/打順を終えない', () => {
    const c = context()
    const q = request({
      eventKind: 'batting-result',
      pitchEventKind: 'pitch-event',
      primaryResultId: 'batting-result.ball',
      byRunner: { first: allAdvance().first, second: allAdvance().second },
    })
    const actual = deriveRunnerOperation(c.before, c.board, q, live, cursors)!
    expect(actual.after).toEqual({
      stateFields: { ...c.before, balls: 2n, runners: 'second-third' },
      scoreboard: c.board,
      battingOrderBySide: cursors,
    })
    expect(actual.countEffect).toEqual({
      strikes: { kind: 'unchanged', value: 0n },
      balls: { kind: 'delta', value: 1n },
    })
    expect(actual.plateAppearanceEnded).toBe(false)
    expect(actual.statFlags.投球数).toBe(true)
    expect(actual.statFlags.打席).toBe(false)
  })
  it('投球を伴わない明示SBは球数/カウントを加算しない', () => {
    const c = context('first')
    const actual = deriveRunnerOperation(
      c.before,
      c.board,
      request(),
      live.slice(0, 1),
      cursors,
    )!
    expect(actual.after.stateFields).toEqual({ ...c.before, runners: 'second' })
    expect(actual.statFlags.投球数).toBe(false)
    expect(actual.plateAppearanceEnded).toBe('not-applicable')
    expect(actual.runnerBoundOutcomes[0]?.responsiblePitcherId).toBe(oldPitcher)
  })
  it.each(['secondary-result.passed-ball', 'secondary-result.wild-pitch'])(
    '%sの全明示進塁はprimary球数1・有効得点1・打点0',
    (operationId) => {
      const c = context('loaded')
      const q = request({
        eventKind: 'secondary-result',
        operationId,
        pitchEventKind: 'pitch-event',
        primaryResultId: 'batting-result.ball',
        byRunner: allAdvance(),
      })
      const actual = deriveRunnerOperation(
        c.before,
        c.board,
        q,
        loadedLive,
        cursors,
      )!
      expect(actual.after.stateFields).toEqual({
        ...c.before,
        runners: 'second-third',
        balls: 2n,
        away: 1n,
      })
      expect(actual.after.scoreboard).toEqual({ ...c.board, away: 1n })
      expect(actual.runnerDefaultAdvance).toEqual({
        first: { modality: 'optional', destination: 2n },
        second: { modality: 'optional', destination: 3n },
        third: { modality: 'optional', destination: 4n },
      })
      expect(actual.runnerScoreEffects).toEqual([
        { base: 3n, validRun: true, rbiCredited: false },
      ])
      expect(actual.statFlags.投球数).toBe(true)
      expect(actual.statFlags.得点).toBe(true)
      expect(actual.statFlags.失点).toBe(true)
      expect(actual.statFlags.打点).toBe(false)
    },
  )
  it('balk授与のoptionalは任意取消の意味へ変えず、非投球で全員1塁を与える', () => {
    const c = context('loaded')
    const actual = deriveRunnerOperation(
      c.before,
      c.board,
      request({
        eventKind: 'secondary-result',
        operationId: 'secondary-result.balk',
        byRunner: allAdvance(),
      }),
      loadedLive,
      cursors,
    )!
    expect(actual.after.stateFields).toEqual({
      ...c.before,
      runners: 'second-third',
      away: 1n,
    })
    expect(actual.statFlags.投球数).toBe(false)
    expect(actual.statFlags.打点).toBe(false)
    expect(actual.runnerDefaultAdvance.third).toEqual({
      modality: 'optional',
      destination: 4n,
    })
  })
  it('牽制死は対象をoutにし、他のID/責任を付け替えない', () => {
    const c = context()
    const q = request({
      operationId: 'pitcher-pickoff-destination.first',
      byRunner: {
        first: {
          kind: 'out',
          runner: ref(first),
          attempted_base: 'first',
          out_kind: 'pitcher-pickoff-out',
        },
      },
    })
    const actual = deriveRunnerOperation(c.before, c.board, q, live, cursors)!
    expect(actual.after.stateFields).toEqual({
      ...c.before,
      outs: 1n,
      runners: 'second',
    })
    expect(actual.outEffect).toEqual({
      count: 1n,
      targets: [{ kind: 'runner', base: 1n }],
    })
    expect(actual.after.battingOrderBySide).toEqual(cursors)
    expect(actual.statFlags.投球数).toBe(false)
  })
  it('盗塁死の第3outはcount効果をunchangedのまま共通後処理で0にする', () => {
    const c = context('first')
    c.before.outs = 2n
    const q = request({
      byRunner: {
        first: {
          kind: 'out',
          runner: ref(first),
          attempted_base: 'second',
          out_kind: 'caught-stealing',
        },
      },
    })
    const actual = deriveRunnerOperation(
      c.before,
      c.board,
      q,
      live.slice(0, 1),
      cursors,
    )!
    expect(actual.countEffect).toEqual({
      strikes: { kind: 'unchanged', value: 0n },
      balls: { kind: 'unchanged', value: 0n },
    })
    expect(actual.after.stateFields).toEqual({
      ...c.before,
      half: 'bottom',
      outs: 0n,
      strikes: 0n,
      balls: 0n,
      runners: 'empty',
      battingOrder: 5n,
    })
    expect(actual.plateAppearanceEnded).toBe('not-applicable')
    expect(actual.after.battingOrderBySide).toEqual(cursors)
  })
  it.each([
    ['home-before-third-out', true, 1n],
    ['not-before-third-out', false, 0n],
  ] as const)(
    'OUT3時機%sを同じ算入処理/根拠に使う',
    (timing, validRun, score) => {
      const c = context()
      c.before.outs = 2n
      const q = request({
        byRunner: observed(),
        thirdOutObservation: {
          kind: 'other-third-out',
          out_person: ref(first),
        },
        thirdOutTimingByRunner: { second: timing },
      })
      const actual = deriveRunnerOperation(c.before, c.board, q, live, cursors)!
      expect(actual.after.stateFields.away).toBe(score)
      expect(actual.runnerDefaultAdvance.second).toEqual({
        modality: 'optional',
        destination: 4n,
      })
      expect(actual.runnerScoreEffects).toEqual([
        { base: 2n, validRun, rbiCredited: false },
      ])
      expect(actual.statFlags.得点).toBe(validRun)
      expect(actual.statFlags.打点).toBe(false)
    },
  )
  it('OUT3-03前位アピールは時機推測なしに後位得点を除外する', () => {
    const c = context('second-third')
    c.before.outs = 2n
    const people = [live[1]!, loadedLive[2]!]
    const q = request({
      byRunner: {
        second: {
          kind: 'safe-advance',
          runner: ref(second),
          destination: 'home',
        },
        third: {
          kind: 'out',
          runner: ref(third),
          attempted_base: 'home',
          out_kind: 'running-out',
        },
      },
      thirdOutObservation: { kind: 'missed-base-appeal', runner: ref(third) },
    })
    const actual = deriveRunnerOperation(c.before, c.board, q, people, cursors)!
    expect(actual.after.stateFields.away).toBe(0n)
    expect(actual.runnerScoreEffects).toEqual([
      { base: 2n, validRun: false, rbiCredited: false },
    ])
  })
  it('SO-05を既kernelへ渡し、打者1/走者1outとK1の両方を保つ', () => {
    const c = context('first')
    c.before.outs = 1n
    c.before.strikes = 2n
    c.before.balls = 0n
    const q = request({
      eventKind: 'batting-result',
      operationId: 'batting-result.strikeout-double-play',
      pitchEventKind: 'pitch-event',
      byRunner: {
        first: {
          kind: 'out',
          runner: ref(first),
          attempted_base: 'second',
          out_kind: 'caught-stealing',
        },
      },
    })
    const actual = deriveRunnerOperation(
      c.before,
      c.board,
      q,
      live.slice(0, 1),
      cursors,
    )!
    expect(actual.outEffect).toEqual({
      count: 2n,
      targets: [{ kind: 'batter' }, { kind: 'runner', base: 1n }],
    })
    expect(actual.after.stateFields).toEqual({
      ...c.before,
      half: 'bottom',
      outs: 0n,
      strikes: 0n,
      balls: 0n,
      runners: 'empty',
      battingOrder: 5n,
    })
    expect(actual.after.battingOrderBySide).toEqual({ away: 4n, home: 5n })
    expect(actual.after.scoreboard.strikeouts).toBe(1n)
    expect(actual.plateAppearanceEnded).toBe(true)
    expect(actual.statFlags.投球数).toBe(true)
    expect(actual.statFlags.奪三振).toBe(true)
  })
  it('不足時機/過剰out/衝突/誤投球区分/不足primaryを成功へしない', () => {
    const c = context()
    const cases = [
      request(), // 一塁→二塁と未対象二塁走者の衝突
      request({ pitchEventKind: 'pitch-event' }),
      request({
        eventKind: 'secondary-result',
        operationId: 'secondary-result.wild-pitch',
      }),
      request({
        operationId: 'pitcher-pickoff-destination.first',
        pitchEventKind: 'pitch-event',
        primaryResultId: 'batting-result.ball',
      }),
      request({ operationId: 'unknown' }),
    ]
    for (const q of cases)
      expect(
        deriveRunnerOperation(c.before, c.board, q, live, cursors),
      ).toBeNull()
    c.before.outs = 2n
    expect(
      deriveRunnerOperation(
        c.before,
        c.board,
        request({
          byRunner: observed(),
          thirdOutObservation: {
            kind: 'other-third-out',
            out_person: ref(first),
          },
        }),
        live,
        cursors,
      ),
    ).toBeNull()
    expect(
      deriveRunnerOperation(
        c.before,
        c.board,
        request({
          byRunner: {
            first: observed().first,
            second: { ...observed().first, runner: ref(second) },
          },
        }),
        live,
        cursors,
      ),
    ).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'

import {
  evaluateFirstPitchContinuation,
  readContinuationRules,
} from './firstPitchContinuation'
import { derive } from './state'
import type { Derived, Scoreboard, StateFields } from './stateTypes'

function initial(): {
  before: StateFields
  board: Scoreboard
  derived: Derived
} {
  const before: StateFields = {
    half: 'top',
    strikes: 0n,
    balls: 0n,
    outs: 0n,
    runners: 'empty',
    battingOrder: 1n,
    tiebreakActive: false,
    gameEnded: false,
    inning: 1n,
    home: 0n,
    away: 0n,
  }
  const board: Scoreboard = {
    home: 0n,
    away: 0n,
    hits: 0n,
    errors: 0n,
    strikeouts: 0n,
    walks: 0n,
  }
  const derived = derive(before, board, 'batting-result.ball', 'pitch-event')
  if (derived === null) throw new Error('実T1初期評価がない')
  return { before, board, derived }
}
function wire() {
  return {
    regulationInnings: '9',
    extensionLimit: '9',
    coldConditions: [],
    tiebreak: null,
    dh: true,
  }
}
function rules() {
  const result = readContinuationRules(wire())
  if (!result.ok) throw new Error('規則読取失敗')
  return result.value
}

describe('初球だけのT2純核', () => {
  it('実R9/L9規則と同じT1評価の全stateを用い、入力を変更しない', () => {
    const { before, board, derived } = initial()
    const original = structuredClone({ before, board, derived })
    const result = evaluateFirstPitchContinuation(
      before,
      board,
      derived,
      rules(),
    )
    expect(result).toEqual({
      kind: 'evaluated-no-end-condition',
      evaluation_point: 'post-play',
      basis: {
        regulation: {
          kind: 'before-regulation-completion',
          regulation_innings: '9',
          observed_inning: '1',
          observed_half: 'top',
        },
        cold: { kind: 'no-configured-cold-condition' },
        extra_and_draw: {
          kind: 'before-extra-inning-boundary',
          configured_extension_limit: '9',
        },
        walk_off: { kind: 'top-half-without-score-change' },
      },
    })
    expect({ before, board, derived }).toEqual(original)
  })
  it.each([
    'half',
    'strikes',
    'outs',
    'runners',
    'battingOrder',
    'tiebreakActive',
    'gameEnded',
    'inning',
    'home',
    'away',
  ] as const)('balls以外のafter.%s変化を未評価へ閉じる', (key) => {
    const { before, board, derived } = initial()
    const next = derived.after.stateFields
    const corrupt = {
      half: 'bottom',
      strikes: 1n,
      outs: 1n,
      runners: 'first',
      battingOrder: 2n,
      tiebreakActive: true,
      gameEnded: true,
      inning: 2n,
      home: 1n,
      away: 1n,
    }
    Object.assign(next, { [key]: corrupt[key] })
    expect(
      evaluateFirstPitchContinuation(before, board, derived, rules()),
    ).toBeNull()
  })
  it.each(['home', 'away', 'hits', 'errors', 'strikeouts', 'walks'] as const)(
    'after scoreboard.%s変化を未評価へ閉じる',
    (key) => {
      const { before, board, derived } = initial()
      derived.after.scoreboard[key] = 1n
      expect(
        evaluateFirstPitchContinuation(before, board, derived, rules()),
      ).toBeNull()
    },
  )
  it.each(['beforeTB', 'afterBalls', 'outEffect', 'PAended', 'R7end'] as const)(
    '%sを代表行の非一致から通常続行にしない',
    (fault) => {
      const { before, board, derived } = initial()
      if (fault === 'beforeTB') before.tiebreakActive = true
      if (fault === 'afterBalls') derived.after.stateFields.balls = 2n
      if (fault === 'outEffect') derived.outEffect.count = 1n
      if (fault === 'PAended') derived.plateAppearanceEnded = true
      if (fault === 'R7end') {
        before.inning = 7n
        derived.after.stateFields.inning = 7n
        before.half = 'bottom'
        derived.after.stateFields.half = 'bottom'
      }
      expect(
        evaluateFirstPitchContinuation(before, board, derived, rules()),
      ).toBeNull()
    },
  )
})

describe('保存規則wire境界', () => {
  it.each([9, true, '09', '9\n', '-0', '1e1', '0', '100', '-1', null])(
    '規則の非canonical/範囲外整数%jを拒否する',
    (bad) => {
      expect(
        readContinuationRules({ ...wire(), regulationInnings: bad }),
      ).toEqual({ ok: false, code: 'INVALID_DECIMAL_INTEGER' })
    },
  )
  it('各objectの余剰キー/欠落と非boolean DHを拒否する', () => {
    for (const key of Object.keys(wire())) {
      const value: Record<string, unknown> = wire()
      delete value[key]
      expect(readContinuationRules(value).ok).toBe(false)
    }
    for (const value of [
      { ...wire(), after: {} },
      { ...wire(), dh: 'true' },
      {
        ...wire(),
        coldConditions: [
          { pointDifference: '7', startInning: '5', extra: true },
        ],
      },
      {
        ...wire(),
        tiebreak: {
          startInning: '10',
          runnerPlacement: 'second',
          leadoffRule: 'continue',
          trusted: true,
        },
      },
    ])
      expect(readContinuationRules(value)).toEqual({
        ok: false,
        code: 'INVALID_REQUEST',
      })
  })
  it('型が正しいcold16件は保持し17件は拒否する', () => {
    const cold = { pointDifference: '7', startInning: '5' }
    expect(
      readContinuationRules({
        ...wire(),
        coldConditions: Array.from({ length: 16 }, () => cold),
      }).ok,
    ).toBe(true)
    expect(
      readContinuationRules({
        ...wire(),
        coldConditions: Array.from({ length: 17 }, () => cold),
      }),
    ).toEqual({ ok: false, code: 'INVALID_REQUEST' })
  })
  it('cold/TBの不正な十進値も補完しない', () => {
    expect(
      readContinuationRules({
        ...wire(),
        coldConditions: [{ pointDifference: '07', startInning: '5' }],
      }),
    ).toEqual({ ok: false, code: 'INVALID_DECIMAL_INTEGER' })
    expect(
      readContinuationRules({
        ...wire(),
        tiebreak: {
          startInning: 10,
          runnerPlacement: 'second',
          leadoffRule: 'continue',
        },
      }),
    ).toEqual({ ok: false, code: 'INVALID_DECIMAL_INTEGER' })
  })
})

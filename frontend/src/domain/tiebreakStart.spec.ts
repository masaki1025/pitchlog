import { describe, expect, it } from 'vitest'
import {
  deriveTiebreakStart,
  transitionTiebreakStart,
  type TiebreakRestoreContext,
  type TiebreakStartRule,
} from './tiebreakStart'

const rule: TiebreakStartRule = {
  startInning: 10n,
  runnerPlacement: 'no_out_first_second',
  leadoffRule: 'continue_lineup',
}
const batter = '00000000-0000-0000-0000-000000000065'
const pitcher = '00000000-0000-0000-0000-0000000000d3'
const catcher = '00000000-0000-0000-0000-0000000000c9'
const first = '00000000-0000-0000-0000-000000000066'
const second = '00000000-0000-0000-0000-000000000067'
const active = [batter, pitcher, catcher, first, second]

function context(
  inning = 10n,
  tiebreakActive = false,
  runners: 'empty' | 'first-second' = 'empty',
  outs = 0n,
  battingOrder = 4n,
): TiebreakRestoreContext {
  return {
    current: {
      stateFields: {
        half: 'top',
        strikes: 0n,
        balls: 0n,
        outs,
        runners,
        battingOrder,
        tiebreakActive,
        gameEnded: false,
        inning,
        home: 0n,
        away: 0n,
      },
      scoreboard: { inningScores: { home: '0', away: '0' } },
    },
    participants: {
      batterId: batter,
      pitcherId: pitcher,
      catcherId: catcher,
      battingOrder: String(battingOrder),
    },
    runners: [],
    lineup: { away: {}, home: {} },
    responsibility: { kind: 'no-change' },
  }
}

function selection() {
  return { firstRunnerId: first, secondRunnerId: second }
}

describe('タイブレーク開始の製品遷移', () => {
  it('P1=Aの実選手IDとP2=Aの半回開始投手で配置する', () => {
    const result = transitionTiebreakStart(context(), rule, selection(), active)
    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.afterContext.current.stateFields.runners).toBe('first-second')
    expect(result.afterContext.current.stateFields.tiebreakActive).toBe(true)
    expect(result.afterContext.participants.batterId).toBe(batter)
    expect(result.afterContext.participants.pitcherId).toBe(pitcher)
    expect(result.afterContext.runners).toEqual([
      {
        runnerId: first,
        responsiblePitcherId: pitcher,
        base: '1',
        status: '継続',
        statusSource: 'auto',
      },
      {
        runnerId: second,
        responsiblePitcherId: pitcher,
        base: '2',
        status: '継続',
        statusSource: 'auto',
      },
    ])
  })

  it('P3=Aは発動後の次半回でも同じ規則で再配置できる', () => {
    const result = transitionTiebreakStart(
      context(11n, true),
      rule,
      { firstRunnerId: second, secondRunnerId: first },
      active,
    )
    expect(result.ok).toBe(true)
  })

  it('同半回の二重配置・途中アウト後・空でない塁を拒否する', () => {
    expect(
      transitionTiebreakStart(
        context(10n, false, 'first-second'),
        rule,
        selection(),
        active,
      ),
    ).toEqual({ ok: false, error: 'runners-not-empty' })
    expect(
      transitionTiebreakStart(
        context(10n, false, 'empty', 1n),
        rule,
        selection(),
        active,
      ),
    ).toEqual({ ok: false, error: 'runners-not-empty' })
  })

  it('規則に適合しない塁・先頭打者・選手IDを拒否する', () => {
    expect(
      transitionTiebreakStart(
        context(),
        { ...rule, runnerPlacement: 'second-third' },
        selection(),
        active,
      ),
    ).toEqual({ ok: false, error: 'not-tiebreak-inning' })
    expect(
      transitionTiebreakStart(context(9n), rule, selection(), active),
    ).toEqual({ ok: false, error: 'not-tiebreak-inning' })
    const mismatchedLeadoff = context()
    mismatchedLeadoff.participants.battingOrder = '9'
    expect(
      transitionTiebreakStart(mismatchedLeadoff, rule, selection(), active),
    ).toEqual({ ok: false, error: 'invalid-leadoff' })
    expect(
      transitionTiebreakStart(
        context(),
        rule,
        { firstRunnerId: first, secondRunnerId: first },
        active,
      ),
    ).toEqual({ ok: false, error: 'duplicate-runner' })
    expect(
      transitionTiebreakStart(
        context(),
        rule,
        {
          firstRunnerId: '00000000-0000-0000-0000-0000000000ff',
          secondRunnerId: second,
        },
        active,
      ),
    ).toEqual({ ok: false, error: 'invalid-runner' })
    expect(
      transitionTiebreakStart(
        context(),
        rule,
        { firstRunnerId: batter, secondRunnerId: second },
        active,
      ),
    ).toEqual({ ok: false, error: 'invalid-runner' })
  })

  it('既存の正式operationRows用の状態効果は不変', () => {
    const before = context().current.stateFields
    const outcome = deriveTiebreakStart(
      before,
      {
        startInning: 10n,
        runnerPlacement: 'first-second',
        leadoffRule: 'continue_lineup',
      },
      { runnerPlacement: 'first-second', leadoffBatter: 4n, inning: 10n },
    )
    expect(outcome.operationResult).toBe('applied')
    expect(outcome.after.runners).toBe('first-second')
    expect(outcome.after.battingOrder).toBe(4n)
    expect(outcome.historyEffect).toEqual({ pushes: false, kind: null })
  })
})

import { expect, it } from 'vitest'
import { deriveLineupPitch, deriveTerminal } from './state'
import type { Runners, Scoreboard, StateFields } from './stateTypes'

function fixture(runners: Runners, balls: bigint = 3n) {
  const before: StateFields = {
    half: 'top',
    inning: 1n,
    outs: 0n,
    strikes: 1n,
    balls,
    runners,
    battingOrder: 1n,
    tiebreakActive: false,
    gameEnded: false,
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
  return { before, board, cursors: { away: 1n, home: 1n } }
}

it('ADV-02/04: 一三塁の四球は一塁だけ押し出し、三塁は保持する', () => {
  const f = fixture('first-third')
  const value = deriveLineupPitch(
    f.before,
    f.board,
    'batting-result.walk',
    'pitch-event',
    f.cursors,
  )
  expect(value?.runnerDefaultAdvance).toEqual({
    first: { modality: 'forced', destination: 2n },
    second: { modality: 'not-applicable', destination: null },
    third: { modality: 'hold', destination: null },
  })
  expect(value?.after.stateFields.runners).toBe('loaded')
  expect(value?.after.stateFields.away).toBe(0n)
  expect(value?.after.scoreboard.walks).toBe(1n)
  expect(value?.statFlags.打点).toBe(false)
  expect(value?.outEffect).toEqual({ count: 0n, targets: [] })
})

it('RBI-07: 満塁の四球と死球は三塁走者を押し出し、得点と打点を1にする', () => {
  for (const [resultId, balls, walks] of [
    ['batting-result.walk', 3n, 1n],
    ['batting-result.hit-by-pitch', 0n, 0n],
  ] as const) {
    const f = fixture('loaded', balls)
    const value = deriveLineupPitch(
      f.before,
      f.board,
      resultId,
      'pitch-event',
      f.cursors,
    )
    expect(value?.runnerDefaultAdvance).toEqual({
      first: { modality: 'forced', destination: 2n },
      second: { modality: 'forced', destination: 3n },
      third: { modality: 'forced', destination: 4n },
    })
    expect(value?.after.stateFields.runners).toBe('loaded')
    expect(value?.after.stateFields.away).toBe(1n)
    expect(value?.after.scoreboard.away).toBe(1n)
    expect(value?.after.scoreboard.walks).toBe(walks)
    expect(value?.statFlags.得点).toBe(true)
    expect(value?.statFlags.打点).toBe(true)
    expect(value?.after.battingOrderBySide).toEqual({ away: 2n, home: 1n })
  }
})

it('ADV-04: 一塁が空いた二三塁では四球によるフォース連鎖がない', () => {
  const f = fixture('second-third')
  const value = deriveLineupPitch(
    f.before,
    f.board,
    'batting-result.walk',
    'pitch-event',
    f.cursors,
  )
  expect(value?.runnerDefaultAdvance).toEqual({
    first: { modality: 'not-applicable', destination: null },
    second: { modality: 'hold', destination: null },
    third: { modality: 'hold', destination: null },
  })
  expect(value?.after.stateFields.runners).toBe('loaded')
  expect(value?.after.stateFields.away).toBe(0n)
  expect(value?.statFlags.打点).toBe(false)
})

it('旧終端ABIは走者ありを受理せず、四球は3ボール未満で閉拒否する', () => {
  const f = fixture('loaded')
  expect(
    deriveTerminal(
      f.before,
      f.board,
      'batting-result.walk',
      'pitch-event',
    ),
  ).toBeNull()
  expect(
    deriveLineupPitch(
      { ...f.before, balls: 2n },
      f.board,
      'batting-result.walk',
      'pitch-event',
      f.cursors,
    ),
  ).toBeNull()
})

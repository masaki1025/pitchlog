import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { deriveLineupPitch } from './state'
import type { Scoreboard, StateFields } from './stateTypes'

const contract = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/state_transition_contract_v1.json'),
    'utf8',
  ),
) as {
  matrixRows: Array<{
    resultId: string
    outEffect: { count: number; targets: unknown[] }
    statFlags: Record<string, boolean>
  }>
}
const row = contract.matrixRows.find(
  (item) => item.resultId === 'batting-result.strikeout-double-play',
)!
function fixture() {
  const before: StateFields = {
    half: 'top',
    inning: 1n,
    outs: 1n,
    strikes: 2n,
    balls: 0n,
    runners: 'first',
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

it('SO-05の固定一死一塁行は打者と一塁走者を2アウトにし攻守交代する', () => {
  const f = fixture()
  const result = deriveLineupPitch(
    f.before,
    f.board,
    'batting-result.strikeout-double-play',
    'pitch-event',
    f.cursors,
  )
  expect(row.outEffect).toEqual({
    count: 2,
    targets: ['batter', { runner: 1 }],
  })
  expect(result?.outEffect).toEqual({
    count: 2n,
    targets: [{ kind: 'batter' }, { kind: 'runner', base: 1n }],
  })
  expect(result?.statFlags).toEqual(row.statFlags)
  expect(result?.runnerDefaultAdvance.first).toEqual({
    modality: 'hold',
    destination: null,
  })
  expect(result?.after.stateFields).toEqual({
    ...f.before,
    half: 'bottom',
    outs: 0n,
    strikes: 0n,
    balls: 0n,
    runners: 'empty',
    battingOrder: 1n,
  })
  expect(result?.after.battingOrderBySide).toEqual({ away: 2n, home: 1n })
  expect(result?.after.scoreboard.strikeouts).toBe(1n)
})

it('SO-05代表行以外を成功へ補完しない', () => {
  const f = fixture()
  for (const [key, value] of [
    ['outs', 0n],
    ['outs', 2n],
    ['runners', 'empty'],
    ['runners', 'first-second'],
    ['strikes', 1n],
    ['balls', 1n],
  ] as const) {
    const before = { ...f.before, [key]: value }
    expect(
      deriveLineupPitch(
        before,
        f.board,
        'batting-result.strikeout-double-play',
        'pitch-event',
        f.cursors,
      ),
    ).toBeNull()
  }
  expect(
    deriveLineupPitch(
      f.before,
      f.board,
      'batting-result.strikeout-double-play',
      'runner-event',
      f.cursors,
    ),
  ).toBeNull()
})

import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, it } from 'vitest'
import { deriveLineupPitch, deriveStrikeout } from './state'
import type { Scoreboard, StateFields } from './stateTypes'

const contract = JSON.parse(
  readFileSync(
    resolve('../contracts/state-transition/state_transition_contract_v1.json'),
    'utf8',
  ),
) as {
  matrixRows: Array<{
    resultId: string
    statFlags: Record<string, boolean>
  }>
}
const expectedFlags = contract.matrixRows.find(
  (row) => row.resultId === 'batting-result.k3',
)!.statFlags

function fixture(runners: StateFields['runners'] = 'empty') {
  const before: StateFields = {
    half: 'top',
    inning: 1n,
    outs: 0n,
    strikes: 2n,
    balls: 0n,
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

it('SO-04のK3を既T1核で1アウト・23flag・走者holdへ導く', () => {
  for (const runners of ['empty', 'first', 'first-third'] as const) {
    const f = fixture(runners)
    const result = deriveLineupPitch(
      f.before,
      f.board,
      'batting-result.k3',
      'pitch-event',
      f.cursors,
    )
    expect(result?.outEffect).toEqual({ count: 1n, targets: [{ kind: 'batter' }] })
    expect(result?.statFlags).toEqual(expectedFlags)
    expect(result?.after.stateFields).toEqual({
      ...f.before,
      outs: 1n,
      strikes: 0n,
      balls: 0n,
      battingOrder: 2n,
    })
    expect(result?.after.scoreboard.strikeouts).toBe(1n)
    expect(result?.runnerDefaultAdvance.first.modality).toBe(
      runners === 'empty' ? 'not-applicable' : 'hold',
    )
  }
})

it('K3を二ストライク未満・非投球・旧SO-01/02公開入口で受け付けない', () => {
  const f = fixture()
  expect(
    deriveStrikeout(
      f.before,
      f.board,
      'batting-result.k3',
      'pitch-event',
      f.cursors,
    ),
  ).toBeNull()
  for (const strikes of [0n, 1n]) {
    f.before.strikes = strikes
    expect(
      deriveLineupPitch(
        f.before,
        f.board,
        'batting-result.k3',
        'pitch-event',
        f.cursors,
      ),
    ).toBeNull()
  }
  f.before.strikes = 2n
  expect(
    deriveLineupPitch(
      f.before,
      f.board,
      'batting-result.k3',
      'runner-event',
      f.cursors,
    ),
  ).toBeNull()
})

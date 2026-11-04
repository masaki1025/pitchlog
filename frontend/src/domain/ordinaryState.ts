import type { Advance, Runners, Scoreboard, StateFields } from './stateTypes'

/** 通常非終端投球の局所状態型を検査する。実権利・終了規則の評価はしない。 */
export function ordinaryStateSupported(
  before: StateFields,
  board: Scoreboard,
): boolean {
  return (
    (before.half === 'top' || before.half === 'bottom') &&
    before.inning >= 1n &&
    before.outs >= 0n &&
    before.outs <= 2n &&
    before.battingOrder >= 1n &&
    before.battingOrder <= 9n &&
    [
      'empty',
      'first',
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
    ].includes(before.runners) &&
    typeof before.tiebreakActive === 'boolean' &&
    before.gameEnded === false &&
    before.home >= 0n &&
    before.away >= 0n &&
    board.home >= 0n &&
    board.away >= 0n &&
    board.hits >= 0n &&
    board.errors >= 0n &&
    board.strikeouts >= 0n &&
    board.walks >= 0n
  )
}

/** 走者効果を伴わない通常投球だけの在塁保持。移動観測を推測しない。 */
export function ordinaryRunnerHold(runners: Runners, base: string): Advance {
  let occupied = runners === 'loaded'
  if (
    base === 'first' &&
    ['first', 'first-second', 'first-third'].includes(runners)
  )
    occupied = true
  if (
    base === 'second' &&
    ['second', 'first-second', 'second-third'].includes(runners)
  )
    occupied = true
  if (
    base === 'third' &&
    ['third', 'first-third', 'second-third'].includes(runners)
  )
    occupied = true
  if (occupied) return { modality: 'hold', destination: null }
  return { modality: 'not-applicable', destination: null }
}

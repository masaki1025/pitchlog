import { FIRST_BALL_RULE } from './stateRules'
import type { Derived, Scoreboard, StateFields, StatFlags } from './stateTypes'

/** spikeの既23フラグ初期化を再利用し、閉じた型で余分なキーを拒否する。 */
export function emptyFlags(): StatFlags {
  return {
    投球回算入アウト: false,
    投球数: false,
    奪三振: false,
    与四球: false,
    与死球: false,
    被安打: false,
    被本塁打: false,
    失点: false,
    失策: false,
    打席: false,
    打数: false,
    安打: false,
    本塁打: false,
    塁打: false,
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
}

/** 最初の操作単位の状態・実投影だけを受け付ける。 */
function supportedState(before: StateFields, board: Scoreboard): boolean {
  return (
    before.half === 'top' &&
    before.inning === 1n &&
    before.outs === 0n &&
    before.strikes === 0n &&
    before.balls === 0n &&
    before.runners === 'empty' &&
    before.battingOrder === 1n &&
    !before.tiebreakActive &&
    !before.gameEnded &&
    before.home === 0n &&
    before.away === 0n &&
    board.home === 0n &&
    board.away === 0n &&
    board.hits === 0n &&
    board.errors === 0n &&
    board.strikeouts === 0n &&
    board.walks === 0n
  )
}

/** 正規化済みの1球を計算する。未実装操作は値を返さない。 */
export function derive(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
): Derived | null {
  if (resultId !== 'batting-result.ball' || pitchEventKind !== 'pitch-event') {
    return null
  }
  if (!supportedState(before, board)) return null
  const rule = FIRST_BALL_RULE
  const balls = before.balls + rule.ballDelta
  const flags = emptyFlags()
  flags.投球数 = pitchEventKind === 'pitch-event'
  flags.投球回算入アウト = rule.outs > 0n
  flags.打席 = rule.pa === true
  // 打席続行・無走者・無失策のball以外は上で拒否し、残る計数を発生させない。
  return {
    countEffect: {
      strikes: { kind: rule.strikeEffect, value: rule.strikeDelta },
      balls: { kind: rule.ballEffect, value: rule.ballDelta },
    },
    plateAppearanceEnded: rule.pa,
    batterDestination: { kind: rule.batter },
    runnerDefaultAdvance: {
      first: { modality: 'not-applicable', destination: null },
      second: { modality: 'not-applicable', destination: null },
      third: { modality: 'not-applicable', destination: null },
    },
    outEffect: { count: rule.outs, targets: [] },
    statFlags: flags,
    history: { ballsBefore: before.balls, ballsAfter: balls },
    after: {
      stateFields: {
        half: before.half,
        inning: before.inning,
        outs: before.outs + rule.outs,
        strikes: before.strikes + rule.strikeDelta,
        balls: balls,
        runners: before.runners,
        battingOrder: before.battingOrder,
        tiebreakActive: before.tiebreakActive,
        gameEnded: before.gameEnded,
        home: before.home,
        away: before.away,
      },
      scoreboard: {
        home: board.home,
        away: board.away,
        hits: board.hits,
        errors: board.errors,
        strikeouts: board.strikeouts,
        walks: board.walks,
      },
    },
  }
}

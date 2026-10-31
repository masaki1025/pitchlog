import { ordinaryStateSupported, ordinaryRunnerHold } from './ordinaryState'
import {
  FIRST_BALL_RULE,
  ORDINARY_STRIKE_RULE,
  TERMINAL_REACH_RULE,
  TERMINAL_OUT_RULE,
} from './stateRules'
import type {
  BatterKind,
  BattingOrderBySide,
  CountEffectKind,
  Derived,
  Rule,
  Scoreboard,
  StateFields,
  StatFlags,
  StrikeoutDerived,
  Target,
} from './stateTypes'

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
  if (
    !supportedState(before, board) ||
    before.strikes !== 0n ||
    before.balls !== 0n
  )
    return null
  return applyCountRule(before, board, FIRST_BALL_RULE)
}

/** 契約が成立した通常33座標だけを同じカウント核へ渡す。 */
export function deriveOrdinary(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
): Derived | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board)
  )
    return null
  if (before.strikes < 0n || before.balls < 0n) return null
  if (resultId === 'batting-result.ball') {
    if (before.strikes > 2n || before.balls > 2n) return null
    return applyCountRule(before, board, FIRST_BALL_RULE)
  }
  if (
    resultId !== 'batting-result.called-pitch' &&
    resultId !== 'batting-result.swinging-strike' &&
    resultId !== 'batting-result.foul'
  )
    return null
  if (
    resultId === 'batting-result.foul' &&
    before.strikes === 2n &&
    before.balls <= 3n
  ) {
    // 通常非バントの明示結果だけ。K3/SO-04の三振結果へ読み替えない。
    const holdRule: Rule = Object.assign({}, ORDINARY_STRIKE_RULE, {
      strikeEffect: 'unchanged' as CountEffectKind,
      strikeDelta: 0n,
    })
    return applyCountRule(before, board, holdRule)
  }
  if (before.strikes > 1n || before.balls > 3n) return null
  return applyCountRule(before, board, ORDINARY_STRIKE_RULE)
}

/** 受理済みの無走者BB/HBPだけを共有核へ渡す。 */
export function deriveTerminal(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
): Derived | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board) ||
    before.runners !== 'empty' ||
    before.strikes < 0n ||
    before.strikes > 2n ||
    before.balls < 0n ||
    before.balls > 3n ||
    before.home !== board.home ||
    before.away !== board.away
  )
    return null
  if (resultId === 'batting-result.walk') {
    if (before.balls !== 3n) return null
  } else if (resultId !== 'batting-result.hit-by-pitch') return null
  return applyCountRule(before, board, TERMINAL_REACH_RULE, resultId)
}

/** 正規捕球の三振だけを、両cursorを検証して同じ核へ渡す。 */
export function deriveStrikeout(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
  cursors: BattingOrderBySide,
): StrikeoutDerived | null {
  let activeOrder = cursors.away
  if (before.half === 'bottom') activeOrder = cursors.home
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board) ||
    before.strikes !== 2n ||
    before.balls < 0n ||
    before.balls > 3n ||
    before.home !== board.home ||
    before.away !== board.away ||
    (resultId !== 'batting-result.called-strikeout' &&
      resultId !== 'batting-result.swinging-strikeout') ||
    cursors.away < 1n ||
    cursors.away > 9n ||
    cursors.home < 1n ||
    cursors.home > 9n ||
    activeOrder !== before.battingOrder
  )
    return null
  return applyCountRule(before, board, TERMINAL_OUT_RULE, resultId, cursors)
}

function applyCountRule(
  before: StateFields,
  board: Scoreboard,
  rule: Rule,
  resultId: string,
  cursors: BattingOrderBySide,
): StrikeoutDerived
function applyCountRule(
  before: StateFields,
  board: Scoreboard,
  rule: Rule,
  resultId?: string,
): Derived
/** 初球・通常投球・打席終了で共有する単一の遷移計算。 */
function applyCountRule(
  before: StateFields,
  board: Scoreboard,
  rule: Rule,
  resultId: string = '',
  cursors?: BattingOrderBySide,
): Derived | StrikeoutDerived {
  let balls = before.balls + rule.ballDelta
  let strikes = before.strikes + rule.strikeDelta
  if (rule.ballEffect === 'reset') balls = 0n
  if (rule.strikeEffect === 'reset') strikes = 0n
  const walk = resultId === 'batting-result.walk'
  const hitByPitch = resultId === 'batting-result.hit-by-pitch'
  const strikeout =
    resultId === 'batting-result.called-strikeout' ||
    resultId === 'batting-result.swinging-strikeout'
  const flags = emptyFlags()
  flags.投球数 = true
  flags.投球回算入アウト = rule.outs > 0n
  flags.打席 = rule.pa === true
  if (walk) {
    flags.与四球 = true
    flags.四球 = true
  }
  if (hitByPitch) {
    flags.与死球 = true
    flags.死球 = true
  }
  if (strikeout) {
    flags.奪三振 = true
    flags.三振 = true
    flags.打数 = true
  }
  // 出塁は無走者の受理済み操作に限定。走者の帰属/保存は補完しない。
  const destination: { kind: BatterKind; base?: bigint } = { kind: rule.batter }
  let runners = before.runners
  let battingOrder = before.battingOrder
  let walks = board.walks
  if (rule.batter === 'reach') {
    destination.base = rule.batterBase
    runners = 'first'
  }
  if (rule.pa === true) battingOrder = (before.battingOrder % 9n) + 1n
  if (walk) walks = board.walks + 1n
  let outs = before.outs + rule.outs
  let half = before.half
  let inning = before.inning
  let orders: { away: bigint; home: bigint } | null = null
  if (typeof cursors !== 'undefined')
    orders = { away: cursors.away, home: cursors.home }
  if (orders !== null) {
    if (before.half === 'top') orders.away = battingOrder
    else orders.home = battingOrder
  }
  if (outs === 3n) {
    outs = 0n
    strikes = 0n
    balls = 0n
    runners = 'empty'
    if (half === 'top') half = 'bottom'
    else {
      half = 'top'
      inning = inning + 1n
    }
    if (orders !== null) {
      if (half === 'top') battingOrder = orders.away
      else battingOrder = orders.home
    }
  }
  let strikeouts = board.strikeouts
  if (strikeout) strikeouts = strikeouts + 1n
  let targets: Array<Target> = []
  if (rule.targets.includes('batter'))
    targets = targets.concat([{ kind: 'batter' }])
  const after = {
    stateFields: {
      half: half,
      inning: inning,
      outs: outs,
      strikes: strikes,
      balls: balls,
      runners: runners,
      battingOrder: battingOrder,
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
      strikeouts: strikeouts,
      walks: walks,
    },
  }
  if (orders !== null)
    Object.assign(after, { battingOrderBySide: Object.freeze(orders) })
  return {
    countEffect: {
      strikes: { kind: rule.strikeEffect, value: rule.strikeDelta },
      balls: { kind: rule.ballEffect, value: rule.ballDelta },
    },
    plateAppearanceEnded: rule.pa,
    batterDestination: destination,
    runnerDefaultAdvance: {
      first: ordinaryRunnerHold(before.runners, 'first'),
      second: ordinaryRunnerHold(before.runners, 'second'),
      third: ordinaryRunnerHold(before.runners, 'third'),
    },
    outEffect: {
      count: rule.outs,
      targets: targets,
    },
    statFlags: flags,
    history: {
      ballsBefore: before.balls,
      ballsAfter: balls,
      strikesBefore: before.strikes,
      strikesAfter: strikes,
    },
    after: after,
  }
}

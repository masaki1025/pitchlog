import { hasRunner } from './runnerOccupancy'
import {
  battedHitRule,
  type BattedHitObservation,
  type BattedHitDerived,
} from './battedHit'
import { ordinaryStateSupported } from './ordinaryState'
import {
  FIRST_BALL_RULE,
  ORDINARY_STRIKE_RULE,
  TERMINAL_REACH_RULE,
  TERMINAL_OUT_RULE,
} from './stateRules'
import type {
  Advance,
  BatterKind,
  BattingOrderBySide,
  CountEffectKind,
  Derived,
  Runners,
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
/** 旧通常ABIはcursorなしで同一scope/返値を保持する。 */
export function deriveOrdinary(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
): Derived | null {
  return deriveOrdinaryCore(before, board, resultId, pitchEventKind)
}
/** 旧終端ABIはcursorなしで同一scope/返値を保持する。 */
export function deriveTerminal(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
): Derived | null {
  return deriveTerminalCore(before, board, resultId, pitchEventKind)
}
/** v3の全投球は両cursorを同じ唯一核へ渡す。旧入口のshapeを広げない。 */
export function deriveLineupPitch(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
  cursors: BattingOrderBySide,
): StrikeoutDerived | null {
  let active = cursors.away
  if (before.half === 'bottom') active = cursors.home
  if (
    cursors.away < 1n ||
    cursors.away > 9n ||
    cursors.home < 1n ||
    cursors.home > 9n ||
    active !== before.battingOrder
  )
    return null
  if (
    resultId === 'batting-result.called-strikeout' ||
    resultId === 'batting-result.swinging-strikeout' ||
    resultId === 'batting-result.k3'
  )
    return deriveClosedStrikeout(
      before,
      board,
      resultId,
      pitchEventKind,
      cursors,
    )
  if (resultId === 'batting-result.strikeout-double-play')
    return deriveStrikeoutDoublePlay(before, board, pitchEventKind, cursors)
  if (
    resultId === 'batting-result.walk' ||
    resultId === 'batting-result.hit-by-pitch'
  )
    return deriveTerminalCore(
      before,
      board,
      resultId,
      pitchEventKind,
      cursors,
      true,
    ) as StrikeoutDerived | null
  return deriveOrdinaryCore(
    before,
    board,
    resultId,
    pitchEventKind,
    cursors,
  ) as StrikeoutDerived | null
}

function deriveOrdinaryCore(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
  cursors?: BattingOrderBySide,
): Derived | StrikeoutDerived | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board)
  )
    return null
  if (before.strikes < 0n || before.balls < 0n) return null
  if (resultId === 'batting-result.ball') {
    if (before.strikes > 2n || before.balls > 2n) return null
    return applyCountRule(before, board, FIRST_BALL_RULE, resultId, cursors)
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
    return applyCountRule(before, board, holdRule, resultId, cursors)
  }
  if (before.strikes > 1n || before.balls > 3n) return null
  return applyCountRule(before, board, ORDINARY_STRIKE_RULE, resultId, cursors)
}

/** 旧終端ABIは無走者を保ち、v3だけはADV-02/RBI-07の連鎖を渡す。 */
function deriveTerminalCore(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
  cursors?: BattingOrderBySide,
  lineupRunners: boolean = false,
): Derived | StrikeoutDerived | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board) ||
    (!lineupRunners && before.runners !== 'empty') ||
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
  return applyCountRule(before, board, TERMINAL_REACH_RULE, resultId, cursors)
}

/** 正規捕球の三振だけを、両cursorを検証して同じ核へ渡す。 */
export function deriveStrikeout(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string,
  cursors: BattingOrderBySide,
): StrikeoutDerived | null {
  if (
    resultId !== 'batting-result.called-strikeout' &&
    resultId !== 'batting-result.swinging-strikeout'
  )
    return null
  return deriveClosedStrikeout(before, board, resultId, pitchEventKind, cursors)
}

/** 既正式SO-01/02と、v3だけのSO-04を同じT1核へ渡す。 */
function deriveClosedStrikeout(
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
      resultId !== 'batting-result.swinging-strikeout' &&
      resultId !== 'batting-result.k3') ||
    cursors.away < 1n ||
    cursors.away > 9n ||
    cursors.home < 1n ||
    cursors.home > 9n ||
    activeOrder !== before.battingOrder
  )
    return null
  return applyCountRule(before, board, TERMINAL_OUT_RULE, resultId, cursors)
}

/** SO-05の固定一死一塁行だけ。対象走者は原典行の一塁に限る。 */
function deriveStrikeoutDoublePlay(
  before: StateFields,
  board: Scoreboard,
  pitchEventKind: string,
  cursors: BattingOrderBySide,
): StrikeoutDerived | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    !ordinaryStateSupported(before, board) ||
    before.outs !== 1n ||
    before.runners !== 'first' ||
    before.strikes !== 2n ||
    before.balls !== 0n ||
    before.home !== board.home ||
    before.away !== board.away
  )
    return null
  const rule: Rule = Object.assign({}, TERMINAL_OUT_RULE, {
    outs: 2n,
    targets: ['batter', '1'],
  })
  return applyCountRule(
    before,
    board,
    rule,
    'batting-result.strikeout-double-play',
    cursors,
  )
}

/** 無走者4安打を、確定観測と両cursorを検証して唯一核へ渡す。 */
export function deriveBattedHit(
  before: StateFields,
  board: Scoreboard,
  observation: BattedHitObservation,
  cursors: BattingOrderBySide,
): BattedHitDerived | null {
  const rule = battedHitRule(before, board, observation, cursors)
  if (rule === null) return null
  return applyCountRule(before, board, rule, rule.resultId, cursors)
}

/** 塁番号の走査順（1塁から3塁）。 */
const BASES: Array<bigint> = [1n, 2n, 3n]

/** 塁の占有を既存8値へ戻す。 */
function runnersName(first: boolean, second: boolean, third: boolean): Runners {
  if (first && second && third) return 'loaded'
  if (first && second) return 'first-second'
  if (first && third) return 'first-third'
  if (second && third) return 'second-third'
  if (first) return 'first'
  if (second) return 'second'
  if (third) return 'third'
  return 'empty'
}

/** 塁番号を `explicit` のキーへ写す。 */
function baseKey(base: bigint): string {
  if (base === 1n) return '1'
  if (base === 2n) return '2'
  return '3'
}

/** 進塁先を4（本塁）で頭打ちにする。 */
function cap(destination: bigint): bigint {
  if (destination > 4n) return 4n
  return destination
}

/** 打者の出塁でフォースされる塁か（ADV-02の連鎖）。 */
function forcedByBatter(runners: Runners, base: bigint): boolean {
  if (base === 1n) return true
  if (base === 2n) return hasRunner(runners, 1n)
  return hasRunner(runners, 1n) && hasRunner(runners, 2n)
}

/** フォース連鎖内なら、到達先がさらに先でもforcedを保つ。 */
function isForced(
  base: bigint,
  runners: Runners,
  batterKind: BatterKind,
): boolean {
  return batterKind === 'reach' && forcedByBatter(runners, base)
}

/** ADV-01..04: 起点塁1つ分の進塁計画を返す。 */
function advanceFor(
  base: bigint,
  rule: Rule,
  runners: Runners,
  batterKind: BatterKind,
): Advance {
  if (!hasRunner(runners, base)) {
    return { modality: 'not-applicable', destination: null }
  }
  if (rule.advance === 'hold_all') {
    return { modality: 'hold', destination: null }
  }
  if (rule.advance === 'plus1_all') {
    if (isForced(base, runners, batterKind))
      return { modality: 'forced', destination: cap(base + 1n) }
    return { modality: 'optional', destination: cap(base + 1n) }
  }
  if (rule.advance === 'explicit') {
    const key = baseKey(base)
    const field = Object.getOwnPropertyDescriptor(rule.explicit, key)
    if (
      field &&
      Object.hasOwn(field, 'value') &&
      typeof field.value === 'bigint'
    ) {
      if (isForced(base, runners, batterKind))
        return { modality: 'forced', destination: field.value }
      return { modality: 'optional', destination: field.value }
    }
    return { modality: 'hold', destination: null }
  }
  if (rule.advance === 'force') {
    if (isForced(base, runners, batterKind)) {
      let step = rule.step
      if (step < 1n) step = 1n
      return { modality: 'forced', destination: cap(base + step) }
    }
    if (rule.step > 0n) {
      return { modality: 'optional', destination: cap(base + rule.step) }
    }
    return { modality: 'hold', destination: null }
  }
  return { modality: 'hold', destination: null }
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
function applyCountRule(
  before: StateFields,
  board: Scoreboard,
  rule: Rule,
  resultId: string,
  cursors?: BattingOrderBySide,
): Derived | StrikeoutDerived
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
    resultId === 'batting-result.swinging-strikeout' ||
    resultId === 'batting-result.k3' ||
    resultId === 'batting-result.strikeout-double-play'
  const hit =
    resultId === 'batting-result.single' ||
    resultId === 'batting-result.double' ||
    resultId === 'batting-result.triple' ||
    resultId === 'batting-result.home-run'
  const homeRun = resultId === 'batting-result.home-run'
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
  if (hit) {
    flags.被安打 = true
    flags.安打 = true
    flags.打数 = true
    flags.塁打 = true
  }
  if (homeRun) {
    flags.被本塁打 = true
    flags.本塁打 = true
  }
  const destination: { kind: BatterKind; base?: bigint } = { kind: rule.batter }
  if (rule.batter === 'reach') destination.base = rule.batterBase
  let battingOrder = before.battingOrder
  let walks = board.walks
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
  const plan = {
    first: advanceFor(1n, rule, before.runners, rule.batter),
    second: advanceFor(2n, rule, before.runners, rule.batter),
    third: advanceFor(3n, rule, before.runners, rule.batter),
  }
  let runs = 0n
  let forcedRuns = 0n
  let first = false
  let second = false
  let third = false
  for (const base of BASES) {
    let advance = plan.third
    if (base === 1n) advance = plan.first
    else if (base === 2n) advance = plan.second
    if (advance.modality === 'not-applicable') continue
    if (rule.targets.includes(baseKey(base))) continue
    if (advance.destination === 4n) {
      if (advance.modality === 'forced') forcedRuns = forcedRuns + 1n
      runs = runs + 1n
      continue
    }
    if (advance.destination === null) {
      if (base === 1n) first = true
      if (base === 2n) second = true
      if (base === 3n) third = true
      continue
    }
    if (advance.destination === 1n) first = true
    if (advance.destination === 2n) second = true
    if (advance.destination === 3n) third = true
  }
  if (rule.batter === 'reach') {
    if (rule.batterBase === 1n) first = true
    if (rule.batterBase === 2n) second = true
    if (rule.batterBase === 3n) third = true
  }
  if (rule.batter === 'score') runs = runs + 1n
  let runners = runnersName(first, second, third)
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
  for (const base of BASES)
    if (rule.targets.includes(baseKey(base)))
      targets = targets.concat([{ kind: 'runner', base }])
  let rbi = 0n
  if (homeRun || hit) rbi = runs
  else if (walk || hitByPitch) rbi = forcedRuns
  flags.得点 = runs > 0n
  flags.失点 = runs > 0n
  flags.打点 = rbi > 0n
  // 得点側はbefore.halfで決める。終了判定はこの核で仮定しない。
  let home = before.home
  let away = before.away
  if (runs > 0n) {
    if (before.half === 'top') away = away + runs
    else home = home + runs
  }
  let boardHome = board.home
  let boardAway = board.away
  let hits = board.hits
  if (runs > 0n) {
    boardHome = home
    boardAway = away
  }
  if (hit) hits = hits + 1n
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
      home: home,
      away: away,
    },
    scoreboard: {
      home: boardHome,
      away: boardAway,
      hits: hits,
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
      first: plan.first,
      second: plan.second,
      third: plan.third,
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

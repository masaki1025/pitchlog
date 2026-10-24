import { STATE_RULES } from './stateRules'
import type {
  Advance,
  BatterKind,
  Derived,
  Half,
  Runners,
  Rule,
  Scoreboard,
  StateFields,
  StatFlags,
  Target,
} from './stateTypes'

/** 塁番号の走査順（1 塁から 3 塁）。 */
const BASES: Array<bigint> = [1n, 2n, 3n]

/** 起点塁の占有を返す。 */
function hasRunner(runners: Runners, base: bigint): boolean {
  if (base === 1n) {
    if (
      runners === 'first' ||
      runners === 'first-second' ||
      runners === 'first-third' ||
      runners === 'loaded'
    ) {
      return true
    }
    return false
  }
  if (base === 2n) {
    if (
      runners === 'second' ||
      runners === 'first-second' ||
      runners === 'second-third' ||
      runners === 'loaded'
    ) {
      return true
    }
    return false
  }
  if (
    runners === 'third' ||
    runners === 'first-third' ||
    runners === 'second-third' ||
    runners === 'loaded'
  ) {
    return true
  }
  return false
}

/** 塁の占有を `state.runners` の値域へ写す。 */
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

/** 塁番号を進塁計画のキーへ写す。 */
function planKey(base: bigint): string {
  if (base === 1n) return 'first'
  if (base === 2n) return 'second'
  return 'third'
}

/** 進塁先を 4（本塁）で頭打ちにする。 */
function cap(destination: bigint): bigint {
  if (destination > 4n) return 4n
  return destination
}

/** ADV-01..04: 起点塁 1 つ分の進塁計画を返す。 */
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
    return { modality: 'optional', destination: cap(base + 1n) }
  }
  if (rule.advance === 'explicit') {
    const key = baseKey(base)
    if (Object.prototype.hasOwnProperty.call(rule.explicit, key)) {
      return { modality: 'optional', destination: rule.explicit[key] }
    }
    return { modality: 'hold', destination: null }
  }
  if (rule.advance === 'force') {
    if (batterKind === 'reach') {
      if (forcedByBatter(runners, base)) {
        let step = rule.step
        if (step < 1n) step = 1n
        return { modality: 'forced', destination: cap(base + step) }
      }
    }
    if (rule.step > 0n) {
      return { modality: 'optional', destination: cap(base + rule.step) }
    }
    return { modality: 'hold', destination: null }
  }
  return { modality: 'hold', destination: null }
}

/** 打者の出塁でフォースされる塁か（ADV-02 の連鎖）。 */
function forcedByBatter(runners: Runners, base: bigint): boolean {
  if (base === 1n) return true
  if (base === 2n) return hasRunner(runners, 1n)
  return hasRunner(runners, 1n) && hasRunner(runners, 2n)
}

/** 打点が付く結果か。 */
function isRbiResult(resultId: string): boolean {
  if (resultId === 'batting-result.single') return true
  if (resultId === 'batting-result.double') return true
  if (resultId === 'batting-result.triple') return true
  if (resultId === 'batting-result.sacrifice-bunt') return true
  if (resultId === 'batting-result.sacrifice-fly') return true
  if (resultId === 'batting-result.batted-out') return true
  if (resultId === 'batting-result.fielders-choice') return true
  if (resultId === 'batting-result.batted-reach') return true
  return false
}

/** 四死球のうち打点の押し出しを数える結果か。 */
function isWalkResult(resultId: string): boolean {
  if (resultId === 'batting-result.walk') return true
  if (resultId === 'batting-result.intentional-walk') return true
  if (resultId === 'batting-result.hit-by-pitch') return true
  return false
}

/** 四球（死球を含まない）の結果か。 */
function isWalk(resultId: string): boolean {
  if (resultId === 'batting-result.walk') return true
  if (resultId === 'batting-result.intentional-walk') return true
  return false
}

/** 三振系の結果か。 */
function isStrikeout(resultId: string): boolean {
  if (resultId === 'batting-result.called-strikeout') return true
  if (resultId === 'batting-result.swinging-strikeout') return true
  if (resultId === 'batting-result.dropped-third-strike') return true
  if (resultId === 'batting-result.k3') return true
  if (resultId === 'batting-result.strikeout-double-play') return true
  return false
}

/** 安打の結果か。 */
function isHit(resultId: string): boolean {
  if (resultId === 'batting-result.single') return true
  if (resultId === 'batting-result.double') return true
  if (resultId === 'batting-result.triple') return true
  if (resultId === 'batting-result.home-run') return true
  return false
}

/** アウト対象の一覧を組み立てる（規則表の値は batter と 1 塁のみ）。 */
function targetList(rule: Rule): Array<Target> {
  const batter = rule.targets.includes('batter')
  const firstRunner = rule.targets.includes('1')
  if (batter && firstRunner) {
    return [{ kind: 'batter' }, { kind: 'runner', base: 1n }]
  }
  if (batter) return [{ kind: 'batter' }]
  if (firstRunner) return [{ kind: 'runner', base: 1n }]
  return []
}

/** 23 種の集計フラグを初期化する。 */
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

/** 1 球の遷移（5 面・23 フラグ・遷移後の状態）を導出する。 */
export function derive(
  before: StateFields,
  board: Scoreboard,
  resultId: string,
  pitchEventKind: string | null,
): Derived {
  const rule = STATE_RULES[resultId]
  const batterKind = rule.batter
  const plan: Record<string, Advance> = {
    first: advanceFor(1n, rule, before.runners, batterKind),
    second: advanceFor(2n, rule, before.runners, batterKind),
    third: advanceFor(3n, rule, before.runners, batterKind),
  }
  const firstBase = plan.first
  const secondBase = plan.second
  const thirdBase = plan.third

  let runs = 0n
  let forcedRuns = 0n
  let first = false
  let second = false
  let third = false
  for (const base of BASES) {
    const advance = plan[planKey(base)]
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
  if (batterKind === 'reach') {
    if (rule.batterBase === 1n) first = true
    if (rule.batterBase === 2n) second = true
    if (rule.batterBase === 3n) third = true
  }
  if (batterKind === 'score') {
    runs = runs + 1n
  }

  let rbi = 0n
  if (resultId === 'batting-result.home-run') {
    rbi = runs
  } else {
    if (isWalkResult(resultId)) {
      rbi = forcedRuns
    } else if (isRbiResult(resultId)) {
      rbi = runs
    } else if (resultId === 'batting-result.error') {
      rbi = 0n - runs
    }
  }

  let strikes = before.strikes
  if (rule.strikeEffect === 'delta') strikes = strikes + rule.strikeDelta
  if (rule.strikeEffect === 'reset') strikes = 0n
  let balls = before.balls
  if (rule.ballEffect === 'delta') balls = balls + rule.ballDelta
  if (rule.ballEffect === 'reset') balls = 0n

  let outs = before.outs + rule.outs
  let half: Half = before.half
  let inning = before.inning
  if (outs >= 3n) {
    outs = 0n
    first = false
    second = false
    third = false
    strikes = 0n
    balls = 0n
    if (half === 'top') {
      half = 'bottom'
    } else {
      half = 'top'
      inning = inning + 1n
    }
  }

  let battingOrder = before.battingOrder
  if (rule.pa === true) {
    const remainder = battingOrder % 9n
    battingOrder = remainder + 1n
  }

  let side: 'home' | 'away' = 'home'
  if (before.half === 'top') side = 'away'
  const score = { home: before.home, away: before.away }
  score[side] = score[side] + runs
  const scoreboard: Scoreboard = {
    home: board.home,
    away: board.away,
    hits: board.hits,
    errors: board.errors,
    strikeouts: board.strikeouts,
    walks: board.walks,
  }
  scoreboard[side] = scoreboard[side] + runs

  const flags = emptyFlags()
  flags.投球回算入アウト = rule.outs > 0n
  flags.投球数 = pitchEventKind === 'pitch-event'
  flags.打席 = rule.pa === true
  flags.四球 = isWalk(resultId)
  flags.与四球 = flags.四球
  flags.死球 = resultId === 'batting-result.hit-by-pitch'
  flags.与死球 = flags.死球
  flags.三振 = isStrikeout(resultId)
  flags.奪三振 = flags.三振
  flags.安打 = isHit(resultId)
  flags.被安打 = flags.安打
  flags.本塁打 = resultId === 'batting-result.home-run'
  flags.被本塁打 = flags.本塁打
  flags.塁打 = flags.安打
  if (resultId === 'batting-result.sacrifice-bunt') flags.犠打 = true
  if (resultId === 'batting-result.sacrifice-bunt-error') flags.犠打 = true
  flags.犠飛 = resultId === 'batting-result.sacrifice-fly'
  if (resultId === 'batting-result.error') flags.失策 = true
  if (resultId === 'batting-result.sacrifice-bunt-error') flags.失策 = true
  flags.打撃妨害出塁 = resultId === 'secondary-result.batting-interference'
  flags.走塁妨害出塁 = resultId === 'secondary-result.obstruction'
  flags.得点 = runs > 0n
  flags.失点 = runs > 0n
  flags.打点 = rbi > 0n
  flags.打数 = flags.打席
  if (flags.四球) flags.打数 = false
  if (flags.死球) flags.打数 = false
  if (flags.犠打) flags.打数 = false
  if (flags.犠飛) flags.打数 = false
  if (flags.打撃妨害出塁) flags.打数 = false
  if (flags.走塁妨害出塁) flags.打数 = false

  if (flags.安打) scoreboard.hits = scoreboard.hits + 1n
  if (flags.失策) scoreboard.errors = scoreboard.errors + 1n
  if (flags.三振) scoreboard.strikeouts = scoreboard.strikeouts + 1n
  if (flags.四球) scoreboard.walks = scoreboard.walks + 1n

  const targets = targetList(rule)

  const after: StateFields = {
    half: half,
    strikes: strikes,
    balls: balls,
    outs: outs,
    runners: runnersName(first, second, third),
    battingOrder: battingOrder,
    tiebreakActive: before.tiebreakActive,
    gameEnded: before.gameEnded,
    inning: inning,
    home: score.home,
    away: score.away,
  }

  const destination: { kind: BatterKind; base?: bigint } = { kind: batterKind }
  if (batterKind === 'reach') destination.base = rule.batterBase

  return {
    countEffect: {
      strikes: { kind: rule.strikeEffect, value: rule.strikeDelta },
      balls: { kind: rule.ballEffect, value: rule.ballDelta },
    },
    plateAppearanceEnded: rule.pa,
    batterDestination: destination,
    runnerDefaultAdvance: {
      first: firstBase,
      second: secondBase,
      third: thirdBase,
    },
    outEffect: { count: rule.outs, targets: targets },
    statFlags: flags,
    after: { stateFields: after, scoreboard: scoreboard },
  }
}

import type { Rule, StateFields } from './stateTypes'

/** 正式ball行だけを再利用する。未対応結果は呼出前に拒否する。 */
export const FIRST_BALL_RULE: Rule = {
  pa: false,
  batter: 'continue',
  batterBase: 0n,
  outs: 0n,
  targets: [],
  advance: 'hold_all',
  step: 0n,
  explicit: {},
  strikeEffect: 'unchanged',
  strikeDelta: 0n,
  ballEffect: 'delta',
  ballDelta: 1n,
}

/** 打席が終了しない見逃し・空振り・ファウルの共通カウント規則。 */
export const ORDINARY_STRIKE_RULE: Rule = {
  pa: false,
  batter: 'continue',
  batterBase: 0n,
  outs: 0n,
  targets: [],
  advance: 'hold_all',
  step: 0n,
  explicit: {},
  strikeEffect: 'delta',
  strikeDelta: 1n,
  ballEffect: 'unchanged',
  ballDelta: 0n,
}

/** 無走者の四球・死球に共通の打席終了/出塁規則。 */
export const TERMINAL_REACH_RULE: Rule = {
  pa: true,
  batter: 'reach',
  batterBase: 1n,
  outs: 0n,
  targets: [],
  advance: 'force',
  step: 0n,
  explicit: {},
  strikeEffect: 'reset',
  strikeDelta: 0n,
  ballEffect: 'reset',
  ballDelta: 0n,
}

/** SO-01/02: 正規捕球の三振。K3/SO-05も同じT1核に閉規則を渡す。 */
export const TERMINAL_OUT_RULE: Rule = {
  pa: true,
  batter: 'out',
  batterBase: 0n,
  outs: 1n,
  targets: ['batter'],
  advance: 'hold_all',
  step: 0n,
  explicit: {},
  strikeEffect: 'reset',
  strikeDelta: 0n,
  ballEffect: 'reset',
  ballDelta: 0n,
}

/** 既通常球のカウント規則を選ぶ。状態/boardの共通検査は呼出元で行う。 */
export function ordinaryCountRule(
  before: StateFields,
  resultId: string,
  pitchEventKind: string,
): Rule | null {
  if (
    pitchEventKind !== 'pitch-event' ||
    before.strikes < 0n ||
    before.balls < 0n
  )
    return null
  if (resultId === 'batting-result.ball') {
    if (before.strikes > 2n || before.balls > 2n) return null
    return FIRST_BALL_RULE
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
    const holdRule: Rule = Object.assign({}, ORDINARY_STRIKE_RULE)
    holdRule.strikeEffect = 'unchanged'
    holdRule.strikeDelta = 0n
    return holdRule
  }
  if (before.strikes > 1n || before.balls > 3n) return null
  return ORDINARY_STRIKE_RULE
}

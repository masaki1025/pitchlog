import type { Rule } from './stateTypes'

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

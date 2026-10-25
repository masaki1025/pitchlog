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

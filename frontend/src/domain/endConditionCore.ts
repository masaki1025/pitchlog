import type { ContinuationRules } from './firstPitchContinuation'

/** 終了規則核へ渡す正規化済みの非終端位置。真正な前回lockは呼出側が保持する。 */
export type EndConditionState = {
  inning: bigint
  half: 'top' | 'bottom'
  home: bigint
  away: bigint
  tiebreakActive: boolean
  gameEnded: boolean
}

/** 共通核が実規則から導出した事実。各ABIのformatterは再判定しない。 */
export type EndConditionFacts = {
  regulationInnings: bigint
  inning: bigint
  half: 'top' | 'bottom'
  coldBranches: Array<string>
  drawBranch: string
  tiebreakActive: boolean
  configuredExtensionLimit: bigint | null
}

/** 旧open ABIのscope/返値を保持する共有核adapter。 */
export function evaluateEndConditionNoEnd(
  state: EndConditionState,
  rules: ContinuationRules,
): EndConditionFacts | null {
  if (rules.extensionLimit !== null && state.inning > rules.extensionLimit)
    return null
  if (
    state.half === 'top' &&
    state.inning > rules.regulationInnings &&
    state.home > state.away
  )
    return null
  let expectedTB = false
  if (rules.tiebreak !== null && state.inning >= rules.tiebreak.startInning)
    expectedTB = true
  if (state.tiebreakActive !== expectedTB) return null
  const boundary: EndBoundary = { completedHalf: null, completedInning: null }
  const evaluated = evaluateEndCondition(state, rules, boundary)
  if (
    evaluated === null ||
    (evaluated.outcome !== 'no-end' &&
      evaluated.outcome !== 'tiebreak-continue')
  )
    return null
  const cold = coldEvidence(state, rules, boundary)
  let draw = 'DRAW-07'
  if (rules.extensionLimit !== null) draw = 'DRAW-08'
  return {
    regulationInnings: rules.regulationInnings,
    inning: state.inning,
    half: state.half,
    coldBranches: cold.branches,
    drawBranch: draw,
    tiebreakActive: expectedTB,
    configuredExtensionLimit: rules.extensionLimit,
  }
}

/** 完了した半回をafter位置から推測せず、実遷移から供給する。 */
export type EndBoundary = {
  completedHalf: 'top' | 'bottom' | null
  completedInning: bigint | null
}
type Outcome =
  | 'no-end'
  | 'normal-end'
  | 'extra-continue'
  | 'limit-draw'
  | 'tiebreak-continue'
  | 'cold-end'
  | 'walk-off'
type XMark = 'recorded-score' | 'x-mark'
export type EndDecision = {
  outcome: Outcome
  endConditionDetected: boolean
  lockFurtherPlayInput: boolean
  promptEndDeclaration: boolean
  automaticallyEndsGame: false
  xMark: 'recorded-score' | 'x-mark'
}
/** 全終了規範の検知結果。正式終了の宣言は別操作である。 */
function decision(outcome: Outcome, xMark: XMark): EndDecision {
  let detected = true
  if (
    outcome === 'no-end' ||
    outcome === 'extra-continue' ||
    outcome === 'tiebreak-continue'
  )
    detected = false
  return {
    outcome: outcome,
    endConditionDetected: detected,
    lockFurtherPlayInput: detected,
    promptEndDeclaration: detected,
    automaticallyEndsGame: false,
    xMark: xMark,
  }
}
/** 規則設定の有限域を共有境界で検証する。 */
export function validEndRules(rules: ContinuationRules): boolean {
  if (rules.regulationInnings < 1n || rules.regulationInnings > 99n)
    return false
  let count = 0n
  for (const stage of rules.coldConditions) {
    count = count + 1n
    if (count > 16n || stage.pointDifference < 1n) return false
  }
  if (
    rules.extensionLimit !== null &&
    (rules.extensionLimit < rules.regulationInnings ||
      rules.extensionLimit > 99n)
  )
    return false
  for (const stage of rules.coldConditions) {
    if (
      stage.pointDifference < 1n ||
      stage.pointDifference > 99n ||
      stage.startInning < 1n ||
      stage.startInning > rules.regulationInnings
    )
      return false
  }
  if (
    rules.tiebreak !== null &&
    (rules.tiebreak.startInning <= rules.regulationInnings ||
      rules.tiebreak.startInning > 99n ||
      (rules.extensionLimit !== null &&
        rules.tiebreak.startInning > rules.extensionLimit))
  )
    return false
  return true
}
/** 実半回完了と得点から全6 outcomeを判定する。期待case/IDは参照しない。 */
export function evaluateEndCondition(
  state: EndConditionState,
  rules: ContinuationRules,
  boundary: EndBoundary,
): EndDecision | null {
  if (
    !validEndRules(rules) ||
    state.inning < 1n ||
    state.home < 0n ||
    state.away < 0n ||
    state.gameEnded
  )
    return null
  if ((boundary.completedHalf === null) !== (boundary.completedInning === null))
    return null
  if (boundary.completedInning !== null && boundary.completedInning < 1n)
    return null
  if (
    boundary.completedHalf === 'top' &&
    (state.half !== 'bottom' || boundary.completedInning !== state.inning)
  )
    return null
  if (
    boundary.completedHalf === 'bottom' &&
    (state.half !== 'top' ||
      boundary.completedInning === null ||
      boundary.completedInning + 1n !== state.inning)
  )
    return null
  if (
    rules.extensionLimit !== null &&
    state.inning > rules.extensionLimit &&
    (boundary.completedHalf !== 'bottom' ||
      boundary.completedInning !== rules.extensionLimit)
  )
    return null
  let expectedTB = false
  if (rules.tiebreak !== null && state.inning >= rules.tiebreak.startInning)
    expectedTB = true
  if (
    state.tiebreakActive !== expectedTB &&
    !(
      expectedTB &&
      !state.tiebreakActive &&
      boundary.completedHalf === 'bottom' &&
      rules.tiebreak !== null &&
      state.inning === rules.tiebreak.startInning
    )
  )
    return null
  const cold = coldEvidence(state, rules, boundary).satisfied
  if (cold) {
    let mark: XMark = 'recorded-score'
    if (boundary.completedHalf === 'top') mark = 'x-mark'
    return decision('cold-end', mark)
  }
  if (
    boundary.completedHalf === 'top' &&
    state.inning >= rules.regulationInnings &&
    state.home > state.away
  )
    return decision('normal-end', 'x-mark')
  if (
    boundary.completedHalf === 'bottom' &&
    boundary.completedInning !== null &&
    boundary.completedInning >= rules.regulationInnings
  ) {
    if (state.home !== state.away)
      return decision('normal-end', 'recorded-score')
    if (
      rules.extensionLimit !== null &&
      boundary.completedInning >= rules.extensionLimit
    )
      return decision('limit-draw', 'recorded-score')
    if (rules.tiebreak !== null && state.inning >= rules.tiebreak.startInning)
      return decision('tiebreak-continue', 'recorded-score')
    return decision('extra-continue', 'recorded-score')
  }
  if (
    state.half === 'bottom' &&
    state.inning >= rules.regulationInnings &&
    state.home > state.away
  )
    return decision('walk-off', 'recorded-score')
  if (
    rules.tiebreak !== null &&
    state.tiebreakActive &&
    state.inning >= rules.tiebreak.startInning
  )
    return decision('tiebreak-continue', 'recorded-score')
  return decision('no-end', 'recorded-score')
}

/** 全cold tierを集約する唯一の判定。ABI枝名と終了検知の両方がこれを使用する。 */
function coldEvidence(
  state: EndConditionState,
  rules: ContinuationRules,
  boundary: EndBoundary,
): { branches: Array<string>; satisfied: boolean } {
  let branches: Array<string> = []
  let satisfied = false
  for (const stage of rules.coldConditions) {
    let branch = 'COLD-06'
    if (state.inning < stage.startInning) branch = 'COLD-01'
    else if (state.half === 'top') {
      branch = 'COLD-01'
      if (state.away - state.home >= stage.pointDifference) branch = 'COLD-04'
    } else {
      if (state.home - state.away >= stage.pointDifference) {
        branch = 'COLD-03'
        satisfied = true
      } else if (state.away - state.home >= stage.pointDifference)
        branch = 'COLD-04'
    }
    if (
      boundary.completedHalf === 'bottom' &&
      boundary.completedInning !== null &&
      boundary.completedInning >= stage.startInning &&
      state.away - state.home >= stage.pointDifference
    ) {
      satisfied = true
      branch = 'COLD-05'
    }
    if (
      boundary.completedHalf === 'bottom' &&
      boundary.completedInning !== null &&
      boundary.completedInning >= stage.startInning &&
      state.home - state.away >= stage.pointDifference
    ) {
      satisfied = true
      branch = 'COLD-03'
    }
    branches = branches.concat([branch])
  }
  return { branches: branches, satisfied: satisfied }
}

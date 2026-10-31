import { evaluateEndConditionNoEnd } from './endConditionCore'
export { evaluateEndConditionNoEnd } from './endConditionCore'
export type { EndConditionState, EndConditionFacts } from './endConditionCore'
import { formatDecimalInteger, parseDecimalInteger } from './decimalCodec'
import type { Derived, Scoreboard, StateFields } from './stateTypes'

type TiebreakRule = {
  startInning: bigint
  runnerPlacement: string
  leadoffRule: string
}

/** 保存規則の数値を正規化した値。真正な保存元の照合は接続側が行う。 */
export type ContinuationRules = {
  regulationInnings: bigint
  coldConditions: Array<{ pointDifference: bigint; startInning: bigint }>
  extensionLimit: bigint | null
  tiebreak: TiebreakRule | null
  dh: boolean
}

type RuleRead =
  | { ok: true; value: ContinuationRules }
  | { ok: false; code: 'INVALID_REQUEST' | 'INVALID_DECIMAL_INTEGER' }

/** 閉じたobjectであることを確認する。 */
function object(
  value: unknown,
  keys: Array<string>,
): Record<string, unknown> | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return null
  if (!Object.keys(value).every((key) => keys.includes(key))) return null
  if (!keys.every((key) => Object.prototype.hasOwnProperty.call(value, key)))
    return null
  return value as Record<string, unknown>
}

/** 保存規則の1〜99のcanonical unsigned decimalだけを読む。 */
function ruleInteger(value: unknown): bigint | null {
  const parsed = parseDecimalInteger(value)
  if (parsed === null || parsed < 1n || parsed > 99n) return null
  return parsed
}

/** 保存規則wireの閉形状を読む。型が正しい未対応設定もここでは保持する。 */
export function readContinuationRules(value: unknown): RuleRead {
  const source = object(value, [
    'regulationInnings',
    'coldConditions',
    'extensionLimit',
    'tiebreak',
    'dh',
  ])
  if (
    source === null ||
    typeof source.dh !== 'boolean' ||
    !Array.isArray(source.coldConditions)
  )
    return { ok: false, code: 'INVALID_REQUEST' }
  const regulationInnings = ruleInteger(source.regulationInnings)
  let extensionLimit: bigint | null = null
  if (source.extensionLimit !== null)
    extensionLimit = ruleInteger(source.extensionLimit)
  if (
    regulationInnings === null ||
    (source.extensionLimit !== null && extensionLimit === null)
  )
    return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
  let coldConditions: Array<{
    pointDifference: bigint
    startInning: bigint
  }> = []
  let coldCount = 0n
  for (const item of source.coldConditions) {
    coldCount = coldCount + 1n
    if (coldCount > 16n) return { ok: false, code: 'INVALID_REQUEST' }
    const cold = object(item, ['pointDifference', 'startInning'])
    if (cold === null) return { ok: false, code: 'INVALID_REQUEST' }
    const pointDifference = ruleInteger(cold.pointDifference)
    const startInning = ruleInteger(cold.startInning)
    if (pointDifference === null || startInning === null)
      return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
    coldConditions = coldConditions.concat({
      pointDifference: pointDifference,
      startInning: startInning,
    })
  }
  let tiebreak: TiebreakRule | null = null
  if (source.tiebreak !== null) {
    const configured = object(source.tiebreak, [
      'startInning',
      'runnerPlacement',
      'leadoffRule',
    ])
    if (
      configured === null ||
      typeof configured.runnerPlacement !== 'string' ||
      typeof configured.leadoffRule !== 'string'
    )
      return { ok: false, code: 'INVALID_REQUEST' }
    const startInning = ruleInteger(configured.startInning)
    if (startInning === null)
      return { ok: false, code: 'INVALID_DECIMAL_INTEGER' }
    tiebreak = {
      startInning: startInning,
      runnerPlacement: configured.runnerPlacement,
      leadoffRule: configured.leadoffRule,
    }
  }
  return {
    ok: true,
    value: {
      regulationInnings: regulationInnings,
      extensionLimit: extensionLimit,
      coldConditions: coldConditions,
      tiebreak: tiebreak,
      dh: source.dh,
    },
  }
}

/** 同じT1評価の開始状態と導出後の全状態を比較する。 */
function firstOrdinaryBall(
  before: StateFields,
  board: Scoreboard,
  derived: Derived,
): boolean {
  const after = derived.after.stateFields
  const afterBoard = derived.after.scoreboard
  return (
    before.half === 'top' &&
    before.inning === 1n &&
    before.strikes === 0n &&
    before.balls === 0n &&
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
    board.walks === 0n &&
    after.half === before.half &&
    after.inning === before.inning &&
    after.strikes === before.strikes &&
    after.balls === before.balls + 1n &&
    after.outs === before.outs &&
    after.runners === before.runners &&
    after.battingOrder === before.battingOrder &&
    after.tiebreakActive === before.tiebreakActive &&
    after.gameEnded === before.gameEnded &&
    after.home === before.home &&
    after.away === before.away &&
    afterBoard.home === board.home &&
    afterBoard.away === board.away &&
    afterBoard.hits === board.hits &&
    afterBoard.errors === board.errors &&
    afterBoard.strikeouts === board.strikeouts &&
    afterBoard.walks === board.walks &&
    derived.outEffect.count === 0n &&
    derived.plateAppearanceEnded === false
  )
}

/** 限定入力から4家族を評価する。同じT1評価以外や範囲外を通常続行へ落とさない。 */
export function evaluateFirstPitchContinuation(
  before: StateFields,
  board: Scoreboard,
  derived: Derived,
  rules: ContinuationRules,
): Record<string, unknown> | null {
  if (!firstOrdinaryBall(before, board, derived)) return null
  if (!rules.coldConditions.every(() => false) || rules.tiebreak !== null)
    return null
  if (rules.regulationInnings !== 7n && rules.regulationInnings !== 9n)
    return null
  if (
    rules.extensionLimit !== null &&
    !(rules.regulationInnings === 9n && rules.extensionLimit === 9n)
  )
    return null
  // guardは旧ABIの支持範囲。終了判定そのものは新ABIと同じ唯一の核を通す。
  const facts = evaluateEndConditionNoEnd(before, rules)
  if (facts === null) return null
  let configuredExtensionLimit: string | null = null
  if (facts.configuredExtensionLimit !== null)
    configuredExtensionLimit = formatDecimalInteger(
      facts.configuredExtensionLimit,
    )
  return {
    kind: 'evaluated-no-end-condition',
    evaluation_point: 'post-play',
    basis: {
      regulation: {
        kind: 'before-regulation-completion',
        regulation_innings: formatDecimalInteger(facts.regulationInnings),
        observed_inning: formatDecimalInteger(facts.inning),
        observed_half: facts.half,
      },
      cold: { kind: 'no-configured-cold-condition' },
      extra_and_draw: {
        kind: 'before-extra-inning-boundary',
        configured_extension_limit: configuredExtensionLimit,
      },
      walk_off: { kind: 'top-half-without-score-change' },
    },
  }
}

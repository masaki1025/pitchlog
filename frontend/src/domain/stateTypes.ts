/** T1 状態計算が扱う型。数値はすべて bigint（境界は十進文字列）。 */

/** 攻守。 */
export type Half = 'top' | 'bottom'

/** 塁の占有。 */
export type Runners =
  | 'empty'
  | 'first'
  | 'second'
  | 'third'
  | 'first-second'
  | 'first-third'
  | 'second-third'
  | 'loaded'

/** 打者の行き先。 */
export type BatterKind =
  'continue' | 'reach' | 'out' | 'score' | 'not-applicable'

/** 打席の終了。打席に属さない操作は `not-applicable`。 */
export type PlateAppearanceEnded = boolean | 'not-applicable'

/** 走者の進塁計画の型。 */
export type AdvanceKind = 'hold_all' | 'plus1_all' | 'explicit' | 'force'

/** カウントの効果。 */
export type CountEffectKind = 'delta' | 'reset' | 'unchanged'

/** 結果IDごとの遷移規則。 */
export type Rule = {
  pa: PlateAppearanceEnded
  batter: BatterKind
  batterBase: bigint
  outs: bigint
  targets: Array<string>
  advance: AdvanceKind
  step: bigint
  explicit: Record<string, bigint>
  strikeEffect: CountEffectKind
  strikeDelta: bigint
  ballEffect: CountEffectKind
  ballDelta: bigint
}

/** 遷移前後の状態（契約の `state.*` と同じ意味）。 */
export type StateFields = {
  half: Half
  strikes: bigint
  balls: bigint
  outs: bigint
  runners: Runners
  battingOrder: bigint
  tiebreakActive: boolean
  gameEnded: boolean
  inning: bigint
  home: bigint
  away: bigint
}

/** スコアボード。 */
export type Scoreboard = {
  home: bigint
  away: bigint
  hits: bigint
  errors: bigint
  strikeouts: bigint
  walks: bigint
}

/** 1 塁分の進塁計画。`destination: null` は留保。 */
export type Advance = {
  modality: 'hold' | 'optional' | 'forced' | 'not-applicable'
  destination: bigint | null
}

/** アウトの対象。 */
export type Target = { kind: 'batter' } | { kind: 'runner'; base: bigint }

/** 打撃・投球の集計フラグ（23 種）。 */
export type StatFlags = {
  投球回算入アウト: boolean
  投球数: boolean
  奪三振: boolean
  与四球: boolean
  与死球: boolean
  被安打: boolean
  被本塁打: boolean
  失点: boolean
  失策: boolean
  打席: boolean
  打数: boolean
  安打: boolean
  本塁打: boolean
  塁打: boolean
  犠打: boolean
  犠飛: boolean
  四球: boolean
  死球: boolean
  三振: boolean
  打撃妨害出塁: boolean
  走塁妨害出塁: boolean
  得点: boolean
  打点: boolean
}

/** 1 球の導出結果。 */
export type Derived = {
  countEffect: {
    strikes: { kind: CountEffectKind; value: bigint }
    balls: { kind: CountEffectKind; value: bigint }
  }
  plateAppearanceEnded: PlateAppearanceEnded
  batterDestination: { kind: BatterKind; base?: bigint }
  runnerDefaultAdvance: { first: Advance; second: Advance; third: Advance }
  outEffect: { count: bigint; targets: Array<Target> }
  statFlags: StatFlags
  history: { ballsBefore: bigint; ballsAfter: bigint }
  after: { stateFields: StateFields; scoreboard: Scoreboard }
}

import { hasRunner } from './runnerOccupancy'
import { ordinaryStateSupported } from './ordinaryState'
import type {
  BattingOrderBySide,
  Derived,
  Rule,
  Runners,
  Scoreboard,
  StateFields,
} from './stateTypes'

/** 正本の閉打球結果。公開wireの型ではない。 */
export type BattedHitResultId =
  | 'batting-result.single'
  | 'batting-result.double'
  | 'batting-result.triple'
  | 'batting-result.home-run'
  | 'batting-result.batted-out'
  | 'batting-result.batted-reach'
  | 'batting-result.fielders-choice'
  | 'batting-result.sacrifice-bunt'
  | 'batting-result.sacrifice-fly'

/** 記録者が確定した1走者の実到達塁。停止は写像へ含めない。 */
export type RunnerAdvanceOverride = {
  runnerBase: '1' | '2' | '3'
  destination: '2' | '3' | '4'
}

/** 明示overrideの閉形。空配列は「未確認」として使わない。 */
export type AppliedRunnerAdvanceOverrides = {
  kind: 'applied'
  overrides: Array<RunnerAdvanceOverride>
}

/** T1入力の既存not-appliedと、記録者が確認した明示進塁の候補。 */
export type RunnerAdvanceOverrides =
  'not-applied' | AppliedRunnerAdvanceOverrides

/** 結果から推定せず、記録者が確定した無併発の観測。 */
export type BattedHitObservation = {
  eventKind: 'batting-result'
  resultId: BattedHitResultId
  pitchEventKind: 'pitch-event'
  officialScoringPayload: 'no-error'
  interferenceRuling: 'not-required'
  runnerAdvanceOverrides: RunnerAdvanceOverrides
  thirdOutObservation: 'none' | 'batter-before-first'
}

/** 旧公開Derivedを広げず、新操作で両side cursorを保持する。 */
export type BattedHitDerived = Derived & {
  after: {
    stateFields: StateFields
    scoreboard: Scoreboard
    battingOrderBySide: BattingOrderBySide
  }
}

const OBSERVATION_KEYS: Array<string> = [
  'eventKind',
  'resultId',
  'pitchEventKind',
  'officialScoringPayload',
  'interferenceRuling',
  'runnerAdvanceOverrides',
  'thirdOutObservation',
]

type QualifiedBattedHitRule = Rule & { resultId: BattedHitResultId }

/** 閉検証済み塁番号を唯一の占有helperへ渡す。 */
function occupied(runners: Runners, base: string): boolean {
  return hasRunner(runners, BigInt(base))
}

/** 3塁分の明示override。nullは未指定（hold）を表す。 */
type AppliedOverrides = {
  first: bigint | null
  second: bigint | null
  third: bigint | null
  count: bigint
}

/** 記録者の明示overrideだけを、余剰/欠落/getterなしで読む。 */
function readAppliedOverrides(
  value: unknown,
  before: StateFields,
): AppliedOverrides | null {
  if (
    typeof value !== 'object' ||
    value === null ||
    Array.isArray(value) ||
    !Object.getOwnPropertySymbols(value).every(() => false)
  )
    return null
  const keys = Object.getOwnPropertyNames(value)
  if (
    !keys.every((key) => key === 'kind' || key === 'overrides') ||
    !keys.includes('kind') ||
    !keys.includes('overrides')
  )
    return null
  const kind = Object.getOwnPropertyDescriptor(value, 'kind')
  const overrides = Object.getOwnPropertyDescriptor(value, 'overrides')
  if (
    !kind ||
    !Object.hasOwn(kind, 'value') ||
    kind.value !== 'applied' ||
    !overrides ||
    !Object.hasOwn(overrides, 'value') ||
    !Array.isArray(overrides.value) ||
    !Object.getOwnPropertySymbols(overrides.value).every(() => false)
  )
    return null
  const items = overrides.value as Array<unknown>
  const result: AppliedOverrides = {
    first: null,
    second: null,
    third: null,
    count: 0n,
  }
  for (const item of items) {
    if (
      typeof item !== 'object' ||
      item === null ||
      Array.isArray(item) ||
      !Object.getOwnPropertySymbols(item).every(() => false)
    )
      return null
    const itemKeys = Object.getOwnPropertyNames(item)
    if (
      !itemKeys.every((key) => key === 'runnerBase' || key === 'destination') ||
      !itemKeys.includes('runnerBase') ||
      !itemKeys.includes('destination')
    )
      return null
    const base = Object.getOwnPropertyDescriptor(item, 'runnerBase')
    const destination = Object.getOwnPropertyDescriptor(item, 'destination')
    if (
      !base ||
      !Object.hasOwn(base, 'value') ||
      !destination ||
      !Object.hasOwn(destination, 'value') ||
      typeof base.value !== 'string' ||
      typeof destination.value !== 'string'
    )
      return null
    const baseKey = base.value
    if (
      (baseKey !== '1' && baseKey !== '2' && baseKey !== '3') ||
      !occupied(before.runners, baseKey)
    )
      return null
    let destinationBase: bigint
    if (destination.value === '2') destinationBase = 2n
    else if (destination.value === '3') destinationBase = 3n
    else if (destination.value === '4') destinationBase = 4n
    else return null
    if (destinationBase <= BigInt(baseKey)) return null
    if (baseKey === '1') {
      if (result.first !== null) return null
      result.first = destinationBase
    } else if (baseKey === '2') {
      if (result.second !== null) return null
      result.second = destinationBase
    } else {
      if (result.third !== null) return null
      result.third = destinationBase
    }
    result.count = result.count + 1n
  }
  if (result.count === 0n || result.count > 3n) return null
  return result
}

/** 打者と走者の到達塁が重ならないことを、計算前に閉じて検査する。 */
function destinationsDoNotCollide(
  before: StateFields,
  batterBase: bigint,
  overrides: AppliedOverrides | null,
): boolean {
  let destinations: Array<string> = []
  if (batterBase >= 1n && batterBase <= 3n) {
    destinations = destinations.concat([batterBase.toString()])
  }
  for (const base of ['1', '2', '3']) {
    if (!occupied(before.runners, base)) continue
    let destination = BigInt(base)
    if (overrides !== null) {
      if (base === '1' && overrides.first !== null)
        destination = overrides.first
      if (base === '2' && overrides.second !== null)
        destination = overrides.second
      if (base === '3' && overrides.third !== null)
        destination = overrides.third
    }
    if (destination === 4n) continue
    const key = destination.toString()
    if (destinations.includes(key)) return false
    destinations = destinations.concat([key])
  }
  return true
}

/** 打球の閉結果と実観測/状態が一致した場合だけ共通核へ渡す規則を作る。 */
export function battedHitRule(
  before: StateFields,
  board: Scoreboard,
  observation: unknown,
  cursors: BattingOrderBySide,
): QualifiedBattedHitRule | null {
  if (
    typeof observation !== 'object' ||
    observation === null ||
    Array.isArray(observation) ||
    !Object.getOwnPropertySymbols(observation).every(() => false) ||
    !Object.getOwnPropertyNames(observation).every((key) =>
      OBSERVATION_KEYS.includes(key),
    ) ||
    !OBSERVATION_KEYS.every((key) => {
      const field = Object.getOwnPropertyDescriptor(observation, key)
      return typeof field === 'object' && Object.hasOwn(field, 'value')
    })
  )
    return null
  const value = observation as Record<string, unknown>
  let activeOrder = cursors.away
  if (before.half === 'bottom') activeOrder = cursors.home
  if (
    value.eventKind !== 'batting-result' ||
    value.pitchEventKind !== 'pitch-event' ||
    value.officialScoringPayload !== 'no-error' ||
    value.interferenceRuling !== 'not-required' ||
    (value.thirdOutObservation !== 'none' &&
      value.thirdOutObservation !== 'batter-before-first') ||
    ![
      before.inning,
      before.outs,
      before.battingOrder,
      before.strikes,
      before.balls,
      before.home,
      before.away,
      board.home,
      board.away,
      board.hits,
      board.errors,
      board.strikeouts,
      board.walks,
      cursors.away,
      cursors.home,
    ].every((number) => typeof number === 'bigint') ||
    !ordinaryStateSupported(before, board) ||
    before.tiebreakActive !== false ||
    before.strikes < 0n ||
    before.strikes > 2n ||
    before.balls < 0n ||
    before.balls > 3n ||
    before.home !== board.home ||
    before.away !== board.away ||
    cursors.away < 1n ||
    cursors.away > 9n ||
    cursors.home < 1n ||
    cursors.home > 9n ||
    activeOrder !== before.battingOrder
  )
    return null
  const resultId = value.resultId
  let base: bigint
  switch (resultId) {
    case 'batting-result.single':
    case 'batting-result.batted-reach':
    case 'batting-result.fielders-choice':
      base = 1n
      break
    case 'batting-result.double':
      base = 2n
      break
    case 'batting-result.triple':
      base = 3n
      break
    case 'batting-result.home-run':
      base = 0n
      break
    case 'batting-result.batted-out':
    case 'batting-result.sacrifice-bunt':
    case 'batting-result.sacrifice-fly':
      base = 0n
      break
    default:
      return null
  }
  let batter: 'score' | 'reach' = 'reach'
  if (base === 0n) batter = 'score'
  if (
    resultId === 'batting-result.batted-out' ||
    resultId === 'batting-result.sacrifice-bunt' ||
    resultId === 'batting-result.sacrifice-fly'
  ) {
    let outOverrides: AppliedOverrides | null = null
    if (value.runnerAdvanceOverrides !== 'not-applied') {
      outOverrides = readAppliedOverrides(value.runnerAdvanceOverrides, before)
      if (outOverrides === null) return null
    }
    if (
      (before.runners === 'empty') !== (outOverrides === null) ||
      !destinationsDoNotCollide(before, 0n, outOverrides) ||
      (resultId === 'batting-result.batted-out'
        ? (before.outs === 2n &&
            value.thirdOutObservation !== 'batter-before-first') ||
          (before.outs !== 2n && value.thirdOutObservation !== 'none')
        : before.outs === 2n || value.thirdOutObservation !== 'none') ||
      (resultId === 'batting-result.sacrifice-bunt' &&
        (before.runners !== 'first-second' ||
          outOverrides?.first !== 2n ||
          outOverrides?.second !== 3n ||
          outOverrides?.third !== null)) ||
      (resultId === 'batting-result.sacrifice-fly' &&
        (before.runners !== 'third' ||
          outOverrides?.first !== null ||
          outOverrides?.second !== null ||
          outOverrides?.third !== 4n))
    )
      return null
    let explicit: Record<string, bigint> = {}
    if (outOverrides?.first !== null && outOverrides?.first !== undefined)
      explicit = Object.assign(explicit, { '1': outOverrides.first })
    if (outOverrides?.second !== null && outOverrides?.second !== undefined)
      explicit = Object.assign(explicit, { '2': outOverrides.second })
    if (outOverrides?.third !== null && outOverrides?.third !== undefined)
      explicit = Object.assign(explicit, { '3': outOverrides.third })
    return {
      resultId,
      pa: true,
      batter: 'out',
      batterBase: 0n,
      outs: 1n,
      targets: ['batter'],
      advance: outOverrides === null ? 'hold_all' : 'explicit',
      step: 0n,
      explicit,
      strikeEffect: 'reset',
      strikeDelta: 0n,
      ballEffect: 'reset',
      ballDelta: 0n,
      ...(outOverrides === null
        ? {}
        : {
            validRunnerScoreBases: before.outs === 2n ? [] : ['1', '2', '3'],
            scoringEvidence: true,
          }),
    }
  }
  if (value.thirdOutObservation !== 'none') return null
  let overrides: AppliedOverrides | null = null
  if (value.runnerAdvanceOverrides !== 'not-applied') {
    overrides = readAppliedOverrides(value.runnerAdvanceOverrides, before)
    if (overrides === null) return null
  }
  if (before.runners === 'empty') {
    // 無走者の既存経路へ applied を混ぜない。
    if (overrides !== null) return null
  } else {
    if (overrides === null) return null
    // 出塁で生じるフォース連鎖は、手動の実到達塁が欠ければ確定できない。
    if (
      resultId !== 'batting-result.home-run' &&
      ((occupied(before.runners, '1') && overrides.first === null) ||
        (occupied(before.runners, '1') &&
          occupied(before.runners, '2') &&
          overrides.second === null) ||
        (before.runners === 'loaded' && overrides.third === null))
    )
      return null
    // 本塁打は打者と全走者の生還が原典で確定する。明示値が全員4でなければ拒否。
    if (
      resultId === 'batting-result.home-run' &&
      ((occupied(before.runners, '1') && overrides.first !== 4n) ||
        (occupied(before.runners, '2') && overrides.second !== 4n) ||
        (occupied(before.runners, '3') && overrides.third !== 4n))
    )
      return null
  }
  if (
    (resultId === 'batting-result.batted-reach' ||
      resultId === 'batting-result.fielders-choice') &&
    (before.runners !== 'first-second' ||
      overrides?.first !== 2n ||
      overrides?.second !== 3n ||
      overrides?.third !== null)
  )
    return null
  if (!destinationsDoNotCollide(before, base, overrides)) return null
  let advance: 'hold_all' | 'explicit' = 'hold_all'
  let explicit: Record<string, bigint> = {}
  if (overrides !== null) {
    advance = 'explicit'
    if (overrides.first !== null)
      explicit = Object.assign(explicit, { '1': overrides.first })
    if (overrides.second !== null)
      explicit = Object.assign(explicit, { '2': overrides.second })
    if (overrides.third !== null)
      explicit = Object.assign(explicit, { '3': overrides.third })
  }
  return {
    resultId,
    pa: true,
    batter,
    batterBase: base,
    outs: 0n,
    targets: [],
    advance: advance,
    step: 0n,
    explicit: explicit,
    strikeEffect: 'reset',
    strikeDelta: 0n,
    ballEffect: 'reset',
    ballDelta: 0n,
  }
}

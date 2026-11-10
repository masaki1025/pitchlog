import { hasRunner } from './runnerOccupancy'
import { canonicalContinuationUuid } from './ordinaryPitchContinuation'
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
  | 'batting-result.error'
  | 'batting-result.fielders-choice'
  | 'batting-result.sacrifice-bunt'
  | 'batting-result.sacrifice-fly'
  | 'batting-result.sacrifice-bunt-error'
  | 'batting-result.double-play'
  | 'secondary-result.batting-interference'

/** 記録者が確定した1走者の実到達塁。停止は写像へ含めない。 */
export type RunnerAdvanceOverride = {
  runnerBase: '1' | '2' | '3'
  destination: '1' | '2' | '3' | '4'
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
  eventKind: 'batting-result' | 'secondary-result'
  resultId: BattedHitResultId
  pitchEventKind: 'pitch-event'
  officialScoringPayload: 'no-error' | 'error-recorded'
  interferenceRuling:
    | 'not-required'
    | {
        kind: 'batting-interference'
        adopted:
          | { kind: 'penalty-award' }
          | { kind: 'play-result'; resultId: BattedHitResultId }
        third_base_scoring_attempt:
          | { kind: 'not-required' }
          | { kind: 'observed'; value: 'none' | 'squeeze' | 'steal-home' }
      }
  runnerAdvanceOverrides: RunnerAdvanceOverrides
  thirdOutObservation: 'none' | 'batter-before-first'
  outRunner?: { base: '1'; runnerId: string; outKind: 'force-out' }
  rbiRulingByRunner?: {
    '1'?: 'ordinary-play' | 'kept-running' | 'stopped-and-restarted'
    '2'?: 'ordinary-play' | 'kept-running' | 'stopped-and-restarted'
    '3'?: 'ordinary-play' | 'kept-running' | 'stopped-and-restarted'
  }
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
  'outRunner',
  'rbiRulingByRunner',
]

type QualifiedBattedHitRule = Rule & { resultId: BattedHitResultId }

/** 明示された生還走者の因果だけをRBI maskへ写す。未指定は旧計算互換。 */
function applyRbiRuling(
  rule: QualifiedBattedHitRule,
  field: unknown,
  scoringBases: Array<string>,
): boolean {
  if (field === null) return true
  if (typeof field !== 'object' || !Object.hasOwn(field, 'value')) return false
  const value = (field as { value: unknown }).value
  if (
    typeof value !== 'object' ||
    value === null ||
    Array.isArray(value) ||
    !Object.getOwnPropertySymbols(value).every(() => false) ||
    !scoringBases.some(() => true)
  )
    return false
  const keys = Object.getOwnPropertyNames(value)
  if (
    !keys.every((key) => scoringBases.includes(key)) ||
    !scoringBases.every((base) => keys.includes(base))
  )
    return false
  let credited: Array<string> = []
  for (const key of keys) {
    const entry = Object.getOwnPropertyDescriptor(value, key)
    if (!entry || !Object.hasOwn(entry, 'value')) return false
    if (
      entry.value !== 'ordinary-play' &&
      entry.value !== 'kept-running' &&
      entry.value !== 'stopped-and-restarted'
    )
      return false
    if (entry.value !== 'stopped-and-restarted')
      credited = credited.concat([key])
  }
  rule.validRunnerRbiBases = credited
  rule.scoringEvidence = true
  return true
}

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
    if (destination.value === '1') destinationBase = 1n
    else if (destination.value === '2') destinationBase = 2n
    else if (destination.value === '3') destinationBase = 3n
    else if (destination.value === '4') destinationBase = 4n
    else return null
    if (destinationBase < BigInt(baseKey)) return null
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

/** 裁定原本を余剰・欠落・getterなしの閉objectとして読む。 */
function closedRecord(
  value: unknown,
  keys: Array<string>,
): Record<string, unknown> | null {
  if (
    typeof value !== 'object' ||
    value === null ||
    Array.isArray(value) ||
    !Object.getOwnPropertySymbols(value).every(() => false)
  )
    return null
  const own = Object.getOwnPropertyNames(value)
  if (
    !own.every((key) => keys.includes(key)) ||
    !keys.every((key) => own.includes(key))
  )
    return null
  for (const key of keys) {
    const field = Object.getOwnPropertyDescriptor(value, key)
    if (!field || !Object.hasOwn(field, 'value')) return null
  }
  return value as Record<string, unknown>
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
    !OBSERVATION_KEYS.filter(
      (key) => key !== 'outRunner' && key !== 'rbiRulingByRunner',
    ).every((key) => {
      const field = Object.getOwnPropertyDescriptor(observation, key)
      return typeof field === 'object' && Object.hasOwn(field, 'value')
    })
  )
    return null
  const value = observation as Record<string, unknown>
  let activeOrder = cursors.away
  if (before.half === 'bottom') activeOrder = cursors.home
  if (
    (value.eventKind !== 'batting-result' &&
      value.eventKind !== 'secondary-result') ||
    value.pitchEventKind !== 'pitch-event' ||
    (value.officialScoringPayload !== 'no-error' &&
      value.officialScoringPayload !== 'error-recorded') ||
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
  if (value.eventKind === 'secondary-result') {
    if (
      resultId !== 'secondary-result.batting-interference' ||
      value.officialScoringPayload !== 'no-error' ||
      value.runnerAdvanceOverrides !== 'not-applied' ||
      value.thirdOutObservation !== 'none' ||
      Object.getOwnPropertyDescriptor(value, 'outRunner') ||
      Object.getOwnPropertyDescriptor(value, 'rbiRulingByRunner')
    )
      return null
    const ruling = closedRecord(value.interferenceRuling, [
      'kind',
      'adopted',
      'third_base_scoring_attempt',
    ])
    if (ruling === null || ruling.kind !== 'batting-interference') return null
    const adopted = closedRecord(ruling.adopted, ['kind'])
    if (adopted === null || adopted.kind !== 'penalty-award') return null
    let scoringAttempt: Record<string, unknown> | null = null
    if (occupied(before.runners, '3'))
      scoringAttempt = closedRecord(ruling.third_base_scoring_attempt, [
        'kind',
        'value',
      ])
    else
      scoringAttempt = closedRecord(ruling.third_base_scoring_attempt, ['kind'])
    if (scoringAttempt === null) return null
    if (occupied(before.runners, '3')) {
      if (
        scoringAttempt.kind !== 'observed' ||
        (scoringAttempt.value !== 'none' &&
          scoringAttempt.value !== 'squeeze' &&
          scoringAttempt.value !== 'steal-home')
      )
        return null
    } else if (scoringAttempt.kind !== 'not-required') return null
    let advance: 'force' | 'plus1_all' = 'force'
    if (
      scoringAttempt.value === 'squeeze' ||
      scoringAttempt.value === 'steal-home'
    )
      advance = 'plus1_all'
    return {
      resultId,
      pa: true,
      batter: 'reach',
      batterBase: 1n,
      outs: 0n,
      targets: [],
      advance,
      step: 0n,
      explicit: {},
      strikeEffect: 'reset',
      strikeDelta: 0n,
      ballEffect: 'reset',
      ballDelta: 0n,
      interferenceScoring: 'batting-award',
      scoringEvidence: true,
    }
  }
  if (value.interferenceRuling !== 'not-required') {
    const ruling = closedRecord(value.interferenceRuling, [
      'kind',
      'adopted',
      'third_base_scoring_attempt',
    ])
    if (ruling === null || ruling.kind !== 'batting-interference') return null
    const adopted = closedRecord(ruling.adopted, ['kind', 'resultId'])
    if (
      adopted === null ||
      adopted.kind !== 'play-result' ||
      adopted.resultId !== resultId
    )
      return null
    let scoringAttempt: Record<string, unknown> | null = null
    if (occupied(before.runners, '3'))
      scoringAttempt = closedRecord(ruling.third_base_scoring_attempt, [
        'kind',
        'value',
      ])
    else
      scoringAttempt = closedRecord(ruling.third_base_scoring_attempt, ['kind'])
    if (scoringAttempt === null) return null
    if (occupied(before.runners, '3')) {
      if (
        scoringAttempt.kind !== 'observed' ||
        (scoringAttempt.value !== 'none' &&
          scoringAttempt.value !== 'squeeze' &&
          scoringAttempt.value !== 'steal-home')
      )
        return null
    } else if (scoringAttempt.kind !== 'not-required') return null
    const ordinary = Object.assign({}, value, {
      interferenceRuling: 'not-required',
    })
    const delegated = battedHitRule(before, board, ordinary, cursors)
    if (delegated === null) return null
    // 採用された実プレイも明示裁定としてtyped effect集合を必ず返す。
    // 空集合でも「算入根拠なし」と区別し、server wire headの封印対象にする。
    return Object.assign({}, delegated, { scoringEvidence: true })
  }
  const errorRecorded = value.officialScoringPayload === 'error-recorded'
  if (
    errorRecorded !==
    (resultId === 'batting-result.error' ||
      resultId === 'batting-result.sacrifice-bunt-error')
  )
    return null
  let base: bigint
  switch (resultId) {
    case 'batting-result.single':
    case 'batting-result.batted-reach':
    case 'batting-result.error':
    case 'batting-result.fielders-choice':
    case 'batting-result.sacrifice-bunt-error':
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
    case 'batting-result.double-play':
      base = 0n
      break
    default:
      return null
  }
  let batter: 'score' | 'reach' = 'reach'
  if (base === 0n) batter = 'score'
  const outField = Object.getOwnPropertyDescriptor(value, 'outRunner')
  const rbiDescriptor = Object.getOwnPropertyDescriptor(
    value,
    'rbiRulingByRunner',
  )
  let rbiField: unknown = null
  if (rbiDescriptor) rbiField = rbiDescriptor
  if (resultId === 'batting-result.double-play') {
    if (rbiField !== null) return null
    if (!outField || !Object.hasOwn(outField, 'value')) return null
    const outRunner = outField.value
    if (
      before.runners !== 'first' ||
      before.outs !== 0n ||
      value.runnerAdvanceOverrides !== 'not-applied' ||
      value.thirdOutObservation !== 'none' ||
      typeof outRunner !== 'object' ||
      outRunner === null ||
      Array.isArray(outRunner) ||
      !Object.getOwnPropertySymbols(outRunner).every(() => false)
    )
      return null
    const outKeys = Object.getOwnPropertyNames(outRunner)
    if (
      !outKeys.every(
        (key) => key === 'base' || key === 'runnerId' || key === 'outKind',
      ) ||
      !outKeys.includes('base') ||
      !outKeys.includes('runnerId') ||
      !outKeys.includes('outKind')
    )
      return null
    const outBase = Object.getOwnPropertyDescriptor(outRunner, 'base')
    const outId = Object.getOwnPropertyDescriptor(outRunner, 'runnerId')
    const outKind = Object.getOwnPropertyDescriptor(outRunner, 'outKind')
    if (
      !outBase ||
      !Object.hasOwn(outBase, 'value') ||
      outBase.value !== '1' ||
      !outId ||
      !Object.hasOwn(outId, 'value') ||
      !canonicalContinuationUuid(outId.value) ||
      !outKind ||
      !Object.hasOwn(outKind, 'value') ||
      outKind.value !== 'force-out'
    )
      return null
    return {
      resultId,
      pa: true,
      batter: 'out',
      batterBase: 0n,
      outs: 2n,
      targets: ['batter', '1'],
      advance: 'hold_all',
      step: 0n,
      explicit: {},
      strikeEffect: 'reset',
      strikeDelta: 0n,
      ballEffect: 'reset',
      ballDelta: 0n,
    }
  }
  if (outField) return null
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
    let thirdOutInvalid = false
    if (resultId === 'batting-result.batted-out') {
      if (before.outs === 2n)
        thirdOutInvalid = value.thirdOutObservation !== 'batter-before-first'
      else thirdOutInvalid = value.thirdOutObservation !== 'none'
    } else
      thirdOutInvalid =
        before.outs === 2n || value.thirdOutObservation !== 'none'
    if (
      (before.runners === 'empty') !== (outOverrides === null) ||
      !destinationsDoNotCollide(before, 0n, outOverrides) ||
      thirdOutInvalid ||
      (resultId === 'batting-result.sacrifice-bunt' && outOverrides === null) ||
      (resultId === 'batting-result.sacrifice-bunt' &&
        outOverrides !== null &&
        ((occupied(before.runners, '1') &&
          (outOverrides.first === null || outOverrides.first <= 1n)) ||
          (occupied(before.runners, '2') &&
            (outOverrides.second === null || outOverrides.second <= 2n)) ||
          (occupied(before.runners, '3') &&
            (outOverrides.third === null || outOverrides.third <= 3n)))) ||
      (resultId === 'batting-result.sacrifice-fly' &&
        (outOverrides === null || outOverrides.third !== 4n))
    )
      return null
    let occupiedCount = 0n
    if (occupied(before.runners, '1')) occupiedCount = occupiedCount + 1n
    if (occupied(before.runners, '2')) occupiedCount = occupiedCount + 1n
    if (occupied(before.runners, '3')) occupiedCount = occupiedCount + 1n
    if (
      resultId === 'batting-result.batted-out' &&
      outOverrides !== null &&
      (outOverrides.first === null || outOverrides.first === 1n) &&
      (outOverrides.second === null || outOverrides.second === 2n) &&
      (outOverrides.third === null || outOverrides.third === 3n) &&
      outOverrides.count !== occupiedCount
    )
      return null
    let explicit: Record<string, bigint> = {}
    if (outOverrides !== null) {
      if (outOverrides.first !== null && outOverrides.first !== 1n)
        explicit = Object.assign(explicit, { '1': outOverrides.first })
      if (outOverrides.second !== null && outOverrides.second !== 2n)
        explicit = Object.assign(explicit, { '2': outOverrides.second })
      if (outOverrides.third !== null && outOverrides.third !== 3n)
        explicit = Object.assign(explicit, { '3': outOverrides.third })
    }
    let advance: 'hold_all' | 'explicit' = 'hold_all'
    if (outOverrides !== null) advance = 'explicit'
    const rule: QualifiedBattedHitRule = {
      resultId,
      pa: true,
      batter: 'out',
      batterBase: 0n,
      outs: 1n,
      targets: ['batter'],
      advance,
      step: 0n,
      explicit,
      strikeEffect: 'reset',
      strikeDelta: 0n,
      ballEffect: 'reset',
      ballDelta: 0n,
    }
    if (outOverrides !== null) {
      let validRunnerScoreBases = ['1', '2', '3']
      if (before.outs === 2n) validRunnerScoreBases = []
      rule.validRunnerScoreBases = validRunnerScoreBases
      rule.scoringEvidence = true
    }
    let scoringBases: Array<string> = []
    if (outOverrides !== null && before.outs !== 2n) {
      if (outOverrides.first === 4n) scoringBases = scoringBases.concat(['1'])
      if (outOverrides.second === 4n) scoringBases = scoringBases.concat(['2'])
      if (outOverrides.third === 4n) scoringBases = scoringBases.concat(['3'])
    }
    if (!applyRbiRuling(rule, rbiField, scoringBases)) return null
    return rule
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
  if (resultId === 'batting-result.fielders-choice' && overrides === null)
    return null
  if (
    errorRecorded &&
    ((resultId === 'batting-result.sacrifice-bunt-error' &&
      (before.outs === 2n || overrides === null)) ||
      (overrides !== null &&
        (overrides.first === 4n ||
          overrides.second === 4n ||
          overrides.third === 4n)))
  )
    return null
  if (!destinationsDoNotCollide(before, base, overrides)) return null
  let advance: 'hold_all' | 'explicit' = 'hold_all'
  let explicit: Record<string, bigint> = {}
  if (overrides !== null) {
    advance = 'explicit'
    if (overrides.first !== null && overrides.first !== 1n)
      explicit = Object.assign(explicit, { '1': overrides.first })
    if (overrides.second !== null && overrides.second !== 2n)
      explicit = Object.assign(explicit, { '2': overrides.second })
    if (overrides.third !== null && overrides.third !== 3n)
      explicit = Object.assign(explicit, { '3': overrides.third })
  }
  const rule: QualifiedBattedHitRule = {
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
  if (errorRecorded) rule.errorRecorded = true
  let scoringBases: Array<string> = []
  if (overrides !== null && resultId !== 'batting-result.home-run') {
    if (overrides.first === 4n) scoringBases = scoringBases.concat(['1'])
    if (overrides.second === 4n) scoringBases = scoringBases.concat(['2'])
    if (overrides.third === 4n) scoringBases = scoringBases.concat(['3'])
  }
  if (!applyRbiRuling(rule, rbiField, scoringBases)) return null
  return rule
}

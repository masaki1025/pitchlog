import { hasRunner } from './runnerOccupancy'
import { canonicalContinuationUuid } from './ordinaryPitchContinuation'
import { ordinaryStateSupported } from './ordinaryState'
import { ordinaryCountRule } from './stateRules'
import type { Runners, Rule, StateFields, Scoreboard } from './stateTypes'

/** 正式T1RunnerOutcomeMapV1の起点キー。数値ABIへの写像はここだけで行う。 */
export type RunnerSlot = 'first' | 'second' | 'third'
export type RunnerDestination = 'first' | 'second' | 'third' | 'home'
/** 正式PlayerRefV1。temporaryを現在のofficial IDへ推測解決しない。 */
export type RunnerPlayerRef =
  | { kind: 'official'; player_id: string }
  | { kind: 'temporary'; temporary_id: string }
export type RunnerOutKind =
  | 'force-out'
  | 'pitcher-pickoff-out'
  | 'catcher-pickoff-out'
  | 'caught-stealing'
  | 'running-out'
/** 正式T1RunnerOutcomeV1の閉unionをそのまま保持する。 */
export type RunnerOutcome =
  | { kind: 'hold'; runner: RunnerPlayerRef }
  | {
      kind: 'safe-advance'
      runner: RunnerPlayerRef
      destination: RunnerDestination
    }
  | {
      kind: 'out'
      runner: RunnerPlayerRef
      attempted_base: RunnerDestination
      out_kind: RunnerOutKind
    }
export type RunnerOutcomeMap = {
  first?: RunnerOutcome
  second?: RunnerOutcome
  third?: RunnerOutcome
}
/** v3 sourceから取得する実ID。公開の認可/保存資格ではない。 */
export type LiveRunnerIdentity = {
  base: '1' | '2' | '3'
  runnerId: string
  responsiblePitcherId: string
}
export type BoundRunnerOutcome = {
  slot: RunnerSlot
  base: bigint
  runnerId: string
  responsiblePitcherId: string
  outcome: RunnerOutcome
}

const SLOTS: Array<{
  slot: RunnerSlot
  wireBase: '1' | '2' | '3'
  base: bigint
}> = [
  { slot: 'first', wireBase: '1', base: 1n },
  { slot: 'second', wireBase: '2', base: 2n },
  { slot: 'third', wireBase: '3', base: 3n },
]
const DESTINATIONS: Array<RunnerDestination> = [
  'first',
  'second',
  'third',
  'home',
]
const OUT_KINDS: Array<RunnerOutKind> = [
  'force-out',
  'pitcher-pickoff-out',
  'catcher-pickoff-out',
  'caught-stealing',
  'running-out',
]

function field(value: object, key: string): unknown {
  const property = Object.getOwnPropertyDescriptor(value, key)
  if (!property || !Object.hasOwn(property, 'value')) return null
  return property.value
}

function closedObject(
  value: unknown,
  keys: Array<string>,
): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return null
  for (const key of Object.getOwnPropertyNames(value)) {
    if (!keys.includes(key)) return null
    const property = Object.getOwnPropertyDescriptor(value, key)
    if (!property || !Object.hasOwn(property, 'value')) return null
  }
  if (
    !keys.every((key) => Object.hasOwn(value, key)) ||
    !Object.getOwnPropertySymbols(value).every(() => false)
  )
    return null
  return value as Record<string, unknown>
}

function playerRef(value: unknown): RunnerPlayerRef | null {
  const official = closedObject(value, ['kind', 'player_id'])
  if (
    official !== null &&
    official.kind === 'official' &&
    typeof official.player_id === 'string' &&
    canonicalContinuationUuid(official.player_id)
  )
    return Object.freeze({ kind: 'official', player_id: official.player_id })
  const temporary = closedObject(value, ['kind', 'temporary_id'])
  if (
    temporary !== null &&
    temporary.kind === 'temporary' &&
    typeof temporary.temporary_id === 'string' &&
    canonicalContinuationUuid(temporary.temporary_id)
  )
    return Object.freeze({
      kind: 'temporary',
      temporary_id: temporary.temporary_id,
    })
  return null
}

function outcome(value: unknown): RunnerOutcome | null {
  const hold = closedObject(value, ['kind', 'runner'])
  if (hold !== null && hold.kind === 'hold') {
    const runner = playerRef(hold.runner)
    if (runner === null) return null
    return Object.freeze({ kind: 'hold', runner: runner })
  }
  const advance = closedObject(value, ['kind', 'runner', 'destination'])
  if (
    advance !== null &&
    advance.kind === 'safe-advance' &&
    DESTINATIONS.some((d) => d === advance.destination)
  ) {
    const runner = playerRef(advance.runner)
    if (runner === null) return null
    return Object.freeze({
      kind: 'safe-advance',
      runner: runner,
      destination: advance.destination as RunnerDestination,
    })
  }
  const out = closedObject(value, [
    'kind',
    'runner',
    'attempted_base',
    'out_kind',
  ])
  if (
    out !== null &&
    out.kind === 'out' &&
    DESTINATIONS.some((d) => d === out.attempted_base) &&
    OUT_KINDS.some((kind) => kind === out.out_kind)
  ) {
    const runner = playerRef(out.runner)
    if (runner === null) return null
    return Object.freeze({
      kind: 'out',
      runner: runner,
      attempted_base: out.attempted_base as RunnerDestination,
      out_kind: out.out_kind as RunnerOutKind,
    })
  }
  return null
}

/** 提出された対象だけを同じsourceへ束縛する。未対象を観測済holdへ補完しない。 */
export function bindRunnerOutcomes(
  value: unknown,
  runners: Runners,
  live: Array<LiveRunnerIdentity>,
): Array<BoundRunnerOutcome> | null {
  if (!Array.isArray(live)) return null
  let source: Array<LiveRunnerIdentity> = []
  for (const runner of live) {
    if (
      !SLOTS.some((s) => s.wireBase === runner.base) ||
      !canonicalContinuationUuid(runner.runnerId) ||
      !canonicalContinuationUuid(runner.responsiblePitcherId) ||
      source.some(
        (r) => r.base === runner.base || r.runnerId === runner.runnerId,
      )
    )
      return null
    source = source.concat([runner])
  }
  const wanted = SLOTS.filter((s) => hasRunner(runners, s.base))
  if (
    wanted.some((s) => !source.some((r) => r.base === s.wireBase)) ||
    source.some((r) => !wanted.some((s) => s.wireBase === r.base))
  )
    return null
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return null
  const keys = Object.getOwnPropertyNames(value)
  if (
    keys.every(() => false) ||
    keys.some((key) => !wanted.some((s) => s.slot === key))
  )
    return null
  const record = closedObject(value, keys)
  if (record === null) return null
  let result: Array<BoundRunnerOutcome> = []
  for (const s of wanted) {
    if (!Object.hasOwn(record, s.slot)) continue
    const observed = outcome(field(record, s.slot))
    const actual = source.find((r) => r.base === s.wireBase)
    // 現v3のlive sourceはofficial UUID。temporaryの解決は真正resolverの責務。
    if (
      !actual ||
      observed === null ||
      observed.runner.kind !== 'official' ||
      observed.runner.player_id !== actual.runnerId
    )
      return null
    result = result.concat([
      Object.freeze({
        slot: s.slot,
        base: s.base,
        runnerId: actual.runnerId,
        responsiblePitcherId: actual.responsiblePitcherId,
        outcome: observed,
      }),
    ])
  }
  return Object.freeze(result) as unknown as Array<BoundRunnerOutcome>
}

/** 閉wireの読取後に唯一核へ渡す内部要求。公開の保存資格ではない。 */
export type RunnerRuleRequest = {
  eventKind: 'batting-result' | 'secondary-result' | 'runner-event'
  operationId: string
  pitchEventKind: 'pitch-event' | 'non-pitch-event'
  primaryResultId: string | null
  byRunner: unknown
  thirdOutObservation: unknown
  thirdOutTimingByRunner: unknown
}
export type RunnerRulePlan = {
  rule: Rule | null
  flagResultId: string
  operationId: string
  bound: Array<BoundRunnerOutcome>
}

function destinationBase(destination: RunnerDestination): bigint {
  if (destination === 'first') return 1n
  if (destination === 'second') return 2n
  if (destination === 'third') return 3n
  return 4n
}

function wireBase(base: bigint): string {
  if (base === 1n) return '1'
  if (base === 2n) return '2'
  return '3'
}

function pickoffTarget(operationId: string): bigint | null {
  if (
    operationId === 'pitcher-pickoff-destination.first' ||
    operationId === 'catcher-pickoff-destination.first'
  )
    return 1n
  if (
    operationId === 'pitcher-pickoff-destination.second' ||
    operationId === 'catcher-pickoff-destination.second'
  )
    return 2n
  if (
    operationId === 'pitcher-pickoff-destination.third' ||
    operationId === 'catcher-pickoff-destination.third'
  )
    return 3n
  return null
}

/** OUT3-03/04/05の観測から有効な本塁到達だけを選ぶ。時間やscoreを推測しない。 */
function validRunnerScores(
  bound: Array<BoundRunnerOutcome>,
  totalOuts: bigint,
  rawThird: unknown,
  rawTiming: unknown,
): Array<string> | null {
  const candidates = bound.filter(
    (r) =>
      r.outcome.kind === 'safe-advance' && r.outcome.destination === 'home',
  )
  const timingKeys = ['first', 'second', 'third', 'batter']
  if (
    typeof rawTiming !== 'object' ||
    rawTiming === null ||
    Array.isArray(rawTiming)
  )
    return null
  const timing = closedObject(rawTiming, Object.getOwnPropertyNames(rawTiming))
  if (
    timing === null ||
    !Object.keys(timing).every((key) => timingKeys.includes(key))
  )
    return null
  for (const key of Object.keys(timing))
    if (
      field(timing, key) !== 'home-before-third-out' &&
      field(timing, key) !== 'not-before-third-out'
    )
      return null
  const notRequired = closedObject(rawThird, ['kind'])
  if (totalOuts < 3n) {
    if (
      notRequired === null ||
      (notRequired.kind !== 'none' && notRequired.kind !== 'not-required')
    )
      return null
    return candidates.map((r) => wireBase(r.base))
  }
  if (
    candidates.every(() => false) &&
    notRequired !== null &&
    notRequired.kind === 'not-required'
  )
    return []
  const other = closedObject(rawThird, ['kind', 'out_person'])
  const appeal = closedObject(rawThird, ['kind', 'runner'])
  let outRef: RunnerPlayerRef | null = null
  let missedBase = false
  if (other !== null && other.kind === 'other-third-out')
    outRef = playerRef(other.out_person)
  if (appeal !== null && appeal.kind === 'missed-base-appeal') {
    outRef = playerRef(appeal.runner)
    missedBase = true
  }
  if (outRef === null || outRef.kind !== 'official') return null
  const outId = outRef.player_id
  const out = bound.find(
    (r) => r.runnerId === outId && r.outcome.kind === 'out',
  )
  if (!out) return null
  let result: Array<string> = []
  for (const candidate of candidates) {
    // 前位走者の踏み忘れアピールは時機判定より先に除く（OUT3-03）。
    if (missedBase && out.base > candidate.base) continue
    const observed = field(timing, candidate.slot)
    if (
      observed !== 'home-before-third-out' &&
      observed !== 'not-before-third-out'
    )
      return null
    if (observed === 'home-before-third-out')
      result = result.concat([wireBase(candidate.base)])
  }
  return result
}

/** 走者の明示結果を既単一核のRuleへ形成する。force/責任/得点は別実装しない。 */
export function prepareRunnerRule(
  before: StateFields,
  board: Scoreboard,
  live: Array<LiveRunnerIdentity>,
  input: RunnerRuleRequest,
): RunnerRulePlan | null {
  if (
    [
      before.strikes,
      before.balls,
      before.outs,
      before.inning,
      before.battingOrder,
      before.home,
      before.away,
      board.home,
      board.away,
      board.hits,
      board.errors,
      board.strikeouts,
      board.walks,
    ].some((n) => typeof n !== 'bigint')
  )
    return null
  if (
    !ordinaryStateSupported(before, board) ||
    before.strikes < 0n ||
    before.strikes > 2n ||
    before.balls < 0n ||
    before.balls > 3n ||
    before.home !== board.home ||
    before.away !== board.away
  )
    return null
  const bound = bindRunnerOutcomes(input.byRunner, before.runners, live)
  if (bound === null) return null
  const target = pickoffTarget(input.operationId)
  const steal = input.operationId === 'strategy-category.steal'
  const special =
    input.operationId === 'secondary-result.passed-ball' ||
    input.operationId === 'secondary-result.wild-pitch' ||
    input.operationId === 'secondary-result.balk'
  const doublePlay =
    input.operationId === 'batting-result.strikeout-double-play'
  if (!steal && target === null && !special && !doublePlay) return null
  if (
    target !== null &&
    (input.eventKind !== 'runner-event' ||
      input.pitchEventKind !== 'non-pitch-event')
  )
    return null
  if (
    steal &&
    input.eventKind !== 'runner-event' &&
    input.eventKind !== 'batting-result'
  )
    return null
  if (special && input.eventKind !== 'secondary-result') return null
  // XC-05: runner-event自身のカウント効果を投球の効果へ読み替えない。
  if (
    input.eventKind === 'runner-event' &&
    input.pitchEventKind !== 'non-pitch-event'
  )
    return null
  if (doublePlay) {
    if (
      input.eventKind !== 'batting-result' ||
      input.pitchEventKind !== 'pitch-event' ||
      input.primaryResultId !== null ||
      before.runners !== 'first' ||
      !bound.every(
        (r) =>
          r.slot === 'first' &&
          r.outcome.kind === 'out' &&
          (r.outcome.out_kind === 'caught-stealing' ||
            r.outcome.out_kind === 'running-out'),
      )
    )
      return null
    const valid = validRunnerScores(
      bound,
      3n,
      input.thirdOutObservation,
      input.thirdOutTimingByRunner,
    )
    if (valid === null || valid.some(() => true)) return null
    // SO-05の旧正式kernelへ委譲する。ここで2outを再計算しない。
    return {
      rule: null,
      operationId: input.operationId,
      flagResultId: input.operationId,
      bound: bound,
    }
  }
  const rule: Rule = {
    pa: 'not-applicable',
    batter: 'not-applicable',
    batterBase: 0n,
    outs: 0n,
    targets: [],
    advance: 'explicit',
    step: 0n,
    explicit: {},
    strikeEffect: 'unchanged',
    strikeDelta: 0n,
    ballEffect: 'unchanged',
    ballDelta: 0n,
    pitchEventKind: input.pitchEventKind,
    scoringEvidence: true,
  }
  if (special) rule.pa = false
  let flagResultId = input.operationId
  if (input.pitchEventKind === 'pitch-event') {
    if (
      input.operationId === 'secondary-result.balk' ||
      input.primaryResultId === null
    )
      return null
    const primary = ordinaryCountRule(
      before,
      input.primaryResultId,
      input.pitchEventKind,
    )
    if (primary === null) return null
    flagResultId = input.primaryResultId
    rule.strikeEffect = primary.strikeEffect
    rule.strikeDelta = primary.strikeDelta
    rule.ballEffect = primary.ballEffect
    rule.ballDelta = primary.ballDelta
    if (input.eventKind === 'batting-result') {
      rule.pa = primary.pa
      rule.batter = primary.batter
    }
  } else if (
    input.primaryResultId !== null ||
    (special && input.operationId !== 'secondary-result.balk')
  )
    return null
  if (
    special &&
    live.some((r) => !bound.some((b) => b.runnerId === r.runnerId))
  )
    return null
  for (const runner of bound) {
    const observed = runner.outcome
    if (target !== null && runner.base !== target && observed.kind !== 'hold')
      return null
    if (observed.kind === 'out') {
      if (
        observed.out_kind === 'force-out' ||
        input.operationId === 'secondary-result.balk'
      )
        return null
      if (
        steal &&
        observed.out_kind !== 'caught-stealing' &&
        observed.out_kind !== 'running-out'
      )
        return null
      if (special && observed.out_kind !== 'running-out') return null
      if (target !== null) {
        if (
          input.operationId.startsWith('pitcher-') &&
          observed.out_kind !== 'pitcher-pickoff-out'
        )
          return null
        if (
          input.operationId.startsWith('catcher-') &&
          observed.out_kind !== 'catcher-pickoff-out'
        )
          return null
      }
      rule.outs = rule.outs + 1n
      rule.targets = rule.targets.concat([wireBase(runner.base)])
    } else if (observed.kind === 'safe-advance') {
      const destination = destinationBase(observed.destination)
      if (destination <= runner.base || target !== null) return null
      if (
        input.operationId === 'secondary-result.balk' &&
        destination !== runner.base + 1n
      )
        return null
      if (runner.slot === 'first')
        rule.explicit = Object.assign({}, rule.explicit, { '1': destination })
      if (runner.slot === 'second')
        rule.explicit = Object.assign({}, rule.explicit, { '2': destination })
      if (runner.slot === 'third')
        rule.explicit = Object.assign({}, rule.explicit, { '3': destination })
    } else if (input.operationId === 'secondary-result.balk') return null
  }
  if (target !== null && !bound.some((r) => r.base === target)) return null
  const totalOuts = before.outs + rule.outs
  if (totalOuts > 3n) return null
  let occupied: Array<bigint> = []
  for (const runner of live) {
    const row = SLOTS.find((s) => s.wireBase === runner.base)
    if (!row) return null
    const observed = bound.find((b) => b.runnerId === runner.runnerId)
    if (observed && observed.outcome.kind === 'out') continue
    let afterBase = row.base
    if (observed && observed.outcome.kind === 'safe-advance')
      afterBase = destinationBase(observed.outcome.destination)
    if (afterBase === 4n) continue
    if (occupied.includes(afterBase)) return null
    occupied = occupied.concat([afterBase])
  }
  const scores = validRunnerScores(
    bound,
    totalOuts,
    input.thirdOutObservation,
    input.thirdOutTimingByRunner,
  )
  if (scores === null) return null
  rule.validRunnerScoreBases = scores
  return {
    rule: rule,
    operationId: input.operationId,
    flagResultId: flagResultId,
    bound: bound,
  }
}

/** 正式perPitchの原値を閉検査し、未観測因果を既定値で補完しない。 */
export function readRunnerObservation(
  value: unknown,
  expectedEventKind: unknown,
  expectedResultId: unknown,
  expectedPitchEventKind: unknown,
): RunnerRuleRequest | null {
  const envelope = closedObject(value, ['perPitch', 'primaryResultId'])
  if (envelope === null) return null
  const p = closedObject(envelope.perPitch, [
    'kind',
    'pitchEventKind',
    'resultId',
    'runnerEventPayload',
    'runnerAdvanceOverridesByRunner',
    'thirdOutObservation',
    'thirdOutTimingByRunner',
    'interferenceRuling',
    'officialScoringPayload',
    'rbi',
    'homeTouchOrder',
  ])
  if (
    p === null ||
    p.kind !== expectedEventKind ||
    p.resultId !== expectedResultId ||
    p.pitchEventKind !== expectedPitchEventKind ||
    (p.kind !== 'batting-result' &&
      p.kind !== 'runner-event' &&
      p.kind !== 'secondary-result') ||
    (p.pitchEventKind !== 'pitch-event' &&
      p.pitchEventKind !== 'non-pitch-event') ||
    typeof p.resultId !== 'string' ||
    (envelope.primaryResultId !== null &&
      typeof envelope.primaryResultId !== 'string')
  )
    return null
  const scoring = closedObject(p.officialScoringPayload, ['kind'])
  const interference = closedObject(p.interferenceRuling, ['kind'])
  const rbi = closedObject(p.rbi, [
    'doublePlayRelayError',
    'runnerContinuityByRunner',
    'wouldScoreWithoutErrorByRunner',
    'cause_by_runner',
    'restart_by_runner',
  ])
  const touch = closedObject(p.homeTouchOrder, ['kind'])
  if (
    scoring === null ||
    scoring.kind !== 'no-error' ||
    interference === null ||
    interference.kind !== 'not-required' ||
    rbi === null ||
    rbi.doublePlayRelayError !== 'not-required' ||
    ![
      'runnerContinuityByRunner',
      'wouldScoreWithoutErrorByRunner',
      'cause_by_runner',
      'restart_by_runner',
    ].every((key) => {
      const v = closedObject(field(rbi, key), ['kind'])
      return v !== null && v.kind === 'not-required'
    }) ||
    touch === null ||
    touch.kind !== 'not-required'
  )
    return null
  const noEvent = closedObject(p.runnerEventPayload, ['kind'])
  const event = closedObject(p.runnerEventPayload, [
    'kind',
    'event_kind',
    'by_runner',
  ])
  const noOverrides = closedObject(p.runnerAdvanceOverridesByRunner, ['kind'])
  const overrides = closedObject(p.runnerAdvanceOverridesByRunner, [
    'kind',
    'by_runner',
  ])
  let operationId = p.resultId
  let byRunner: unknown = null
  if (
    p.kind === 'runner-event' ||
    (p.kind === 'batting-result' &&
      p.resultId !== 'batting-result.strikeout-double-play')
  ) {
    if (
      event === null ||
      event.kind !== 'runner-event' ||
      typeof event.event_kind !== 'string' ||
      noOverrides === null ||
      noOverrides.kind !== 'not-applied'
    )
      return null
    operationId = event.event_kind
    byRunner = event.by_runner
    if (p.kind === 'runner-event' && operationId !== p.resultId) return null
    if (p.kind === 'batting-result' && envelope.primaryResultId !== p.resultId)
      return null
  } else {
    if (
      noEvent === null ||
      noEvent.kind !== 'not-applicable' ||
      overrides === null ||
      overrides.kind !== 'overridden'
    )
      return null
    byRunner = overrides.by_runner
  }
  return {
    eventKind: p.kind,
    operationId: operationId,
    pitchEventKind: p.pitchEventKind,
    primaryResultId: envelope.primaryResultId,
    byRunner: byRunner,
    thirdOutObservation: p.thirdOutObservation,
    thirdOutTimingByRunner: p.thirdOutTimingByRunner,
  }
}

import { canonicalContinuationUuid } from './ordinaryPitchContinuation'
import { hasRunner } from './runnerOccupancy'
import { ordinaryStateSupported } from './ordinaryState'
import type { LiveRunnerIdentity } from './runnerEvent'
import type { BattingOrderBySide, Rule, Scoreboard, StateFields } from './stateTypes'

/** 裁定原本と現在の実選手参照。保存資格は後段の正式sourceが検証する。 */
export type InterferenceObservation = {
  eventKind: 'secondary-result'
  resultId: 'secondary-result.obstruction' | 'secondary-result.offensive-interference'
  pitchEventKind: 'pitch-event'
  interferenceRuling: unknown
  batterId: string
  liveRunners: Array<LiveRunnerIdentity>
}

function closed(value: unknown, keys: Array<string>): Record<string, unknown> | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  if (!Object.getOwnPropertySymbols(value).every(() => false)) return null
  const own = Object.getOwnPropertyNames(value)
  if (!own.every((key) => keys.includes(key)) || !keys.every((key) => own.includes(key))) return null
  for (const key of keys) {
    const field = Object.getOwnPropertyDescriptor(value, key)
    if (!field || !Object.hasOwn(field, 'value')) return null
  }
  return value as Record<string, unknown>
}

function sourceRunners(before: StateFields, live: Array<LiveRunnerIdentity>): boolean {
  if (!Array.isArray(live)) return false
  let seen: Array<string> = []
  for (const row of live) {
    const source = closed(row, ['base', 'runnerId', 'responsiblePitcherId'])
    if (
      source === null ||
      (source.base !== '1' && source.base !== '2' && source.base !== '3') ||
      typeof source.runnerId !== 'string' ||
      typeof source.responsiblePitcherId !== 'string' ||
      !canonicalContinuationUuid(source.runnerId) ||
      !canonicalContinuationUuid(source.responsiblePitcherId) ||
      !hasRunner(before.runners, BigInt(source.base)) ||
      seen.includes(source.base) ||
      seen.includes(source.runnerId)
    ) return false
    seen = seen.concat([source.base, source.runnerId])
  }
  for (const base of ['1', '2', '3'])
    if (hasRunner(before.runners, BigInt(base)) !== seen.includes(base)) return false
  return true
}

/** 正式ScorerRefのactual IDを起点塁へ束縛する。temporaryは現sourceに存在しない。 */
function boundPerson(value: unknown, batterId: string, live: Array<LiveRunnerIdentity>): string | null {
  const runner = closed(value, ['kind', 'runner_id'])
  if (runner !== null && runner.kind === 'runner') {
    const ref = closed(runner.runner_id, ['kind', 'player_id'])
    if (ref === null || ref.kind !== 'official' || typeof ref.player_id !== 'string') return null
    const found = live.find((row) => row.runnerId === ref.player_id)
    if (!found) return null
    return found.base
  }
  const batter = closed(value, ['kind', 'batter_id'])
  if (batter !== null && batter.kind === 'batter') {
    const ref = closed(batter.batter_id, ['kind', 'player_id'])
    if (ref !== null && ref.kind === 'official' && ref.player_id === batterId) return 'batter'
  }
  return null
}

function destination(value: unknown): bigint | null {
  if (value === 'first') return 1n
  if (value === 'second') return 2n
  if (value === 'third') return 3n
  if (value === 'home') return 4n
  return null
}

function atMostFour(values: Array<unknown>, required: boolean): boolean {
  let count = 0n
  for (const item of values) {
    if (typeof item === 'undefined') return false
    count = count + 1n
    if (count > 4n) return false
  }
  if (required && count === 0n) return false
  return true
}

function explicitBase(rule: Rule, base: string): bigint | null {
  if (base === '1') {
    const value = Object.getOwnPropertyDescriptor(rule.explicit, '1')
    if (value && Object.hasOwn(value, 'value')) return value.value as bigint
  }
  if (base === '2') {
    const value = Object.getOwnPropertyDescriptor(rule.explicit, '2')
    if (value && Object.hasOwn(value, 'value')) return value.value as bigint
  }
  if (base === '3') {
    const value = Object.getOwnPropertyDescriptor(rule.explicit, '3')
    if (value && Object.hasOwn(value, 'value')) return value.value as bigint
  }
  return null
}

function baseRule(): Rule {
  return {
    pa: false,
    batter: 'continue',
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
    pitchEventKind: 'pitch-event',
    scoringEvidence: true,
  }
}

/** 審判が宣告した対象/到達先だけを唯一核のRuleへ変換する。 */
export function interferenceRule(
  before: StateFields,
  board: Scoreboard,
  observation: unknown,
  cursors: BattingOrderBySide,
): Rule | null {
  const input = closed(observation, [
    'eventKind', 'resultId', 'pitchEventKind', 'interferenceRuling', 'batterId', 'liveRunners',
  ])
  if (
    input === null || input.eventKind !== 'secondary-result' ||
    (input.resultId !== 'secondary-result.obstruction' && input.resultId !== 'secondary-result.offensive-interference') ||
    input.pitchEventKind !== 'pitch-event' || typeof input.batterId !== 'string' ||
    !canonicalContinuationUuid(input.batterId) || !Array.isArray(input.liveRunners) ||
    !sourceRunners(before, input.liveRunners as Array<LiveRunnerIdentity>) ||
    (input.liveRunners as Array<LiveRunnerIdentity>).some((row) => row.runnerId === input.batterId) ||
    !ordinaryStateSupported(before, board) || before.tiebreakActive !== false || before.gameEnded !== false ||
    before.home !== board.home || before.away !== board.away ||
    (before.half === 'top' && cursors.away !== before.battingOrder) ||
    (before.half === 'bottom' && cursors.home !== before.battingOrder)
  ) return null
  const live = input.liveRunners as Array<LiveRunnerIdentity>
  const rule = baseRule()
  const ruling = input.interferenceRuling
  let placements: Array<unknown> = []
  let outTargets: Array<unknown> = []
  if (input.resultId === 'secondary-result.obstruction') {
    const observed = closed(ruling, [
      'kind', 'play_kind', 'obstructed', 'awarded_destinations', 'out_targets', 'batter_before_first',
    ])
    if (
      observed === null || observed.kind !== 'obstruction' ||
      (observed.play_kind !== 'play-on-obstructed-runner' && observed.play_kind !== 'no-play-on-obstructed-runner') ||
      !Array.isArray(observed.awarded_destinations) || !Array.isArray(observed.out_targets) ||
      !atMostFour(observed.awarded_destinations, false) || !atMostFour(observed.out_targets, false) ||
      (observed.batter_before_first !== 'not-required' && observed.batter_before_first !== true && observed.batter_before_first !== false)
    ) return null
    const obstructed = boundPerson(observed.obstructed, input.batterId, live)
    if (obstructed === null) return null
    if (obstructed === 'batter' && observed.batter_before_first !== true) return null
    if (obstructed !== 'batter' && observed.batter_before_first === true) return null
    placements = observed.awarded_destinations
    outTargets = observed.out_targets
    rule.interferenceScoring = 'obstruction-award'
    if (observed.play_kind === 'play-on-obstructed-runner') {
      for (const target of outTargets)
        if (boundPerson(target, input.batterId, live) === obstructed) return null
    }
  } else {
    const observed = closed(ruling, ['kind', 'out_targets', 'return_bases'])
    if (
      observed === null || observed.kind !== 'offensive-interference' ||
      !Array.isArray(observed.out_targets) || !Array.isArray(observed.return_bases) ||
      !atMostFour(observed.out_targets, true) || !atMostFour(observed.return_bases, false)
    ) return null
    placements = observed.return_bases
    outTargets = observed.out_targets
    rule.interferenceScoring = 'offensive-out'
  }
  let targets: Array<string> = []
  let outCount = 0n
  for (const raw of outTargets) {
    const person = boundPerson(raw, input.batterId, live)
    if (person === null || targets.includes(person)) return null
    targets = targets.concat([person])
    outCount = outCount + 1n
  }
  if (before.outs + outCount > 3n) return null
  rule.targets = targets
  rule.outs = outCount
  if (targets.includes('batter')) {
    rule.batter = 'out'
    rule.pa = true
    rule.strikeEffect = 'reset'
    rule.ballEffect = 'reset'
  }
  let placed: Array<string> = []
  let occupied: Array<bigint> = []
  for (const raw of placements) {
    const entry = closed(raw, ['person', 'destination'])
    if (entry === null) return null
    const person = boundPerson(entry.person, input.batterId, live)
    const base = destination(entry.destination)
    if (person === null || base === null || placed.includes(person) || targets.includes(person)) return null
    placed = placed.concat([person])
    if (person === 'batter') {
      if (base === 4n) return null
      rule.batter = 'reach'
      rule.batterBase = base
      rule.pa = true
      rule.strikeEffect = 'reset'
      rule.ballEffect = 'reset'
    } else {
      const origin = BigInt(person)
      if (input.resultId === 'secondary-result.obstruction' && base < origin) return null
      if (input.resultId === 'secondary-result.offensive-interference' && base > origin) return null
      if (base !== origin) {
        if (person === '1') rule.explicit = Object.assign({}, rule.explicit, { '1': base })
        if (person === '2') rule.explicit = Object.assign({}, rule.explicit, { '2': base })
        if (person === '3') rule.explicit = Object.assign({}, rule.explicit, { '3': base })
      }
    }
  }
  if (input.resultId === 'secondary-result.offensive-interference' && placed.includes('batter')) return null
  for (const row of live) {
    if (targets.includes(row.base)) continue
    if (!placed.includes(row.base)) return null
    let afterBase = explicitBase(rule, row.base)
    if (afterBase === null) afterBase = BigInt(row.base)
    if (afterBase !== 4n) {
      if (occupied.includes(afterBase)) return null
      occupied = occupied.concat([afterBase])
    }
  }
  if (rule.batter === 'reach') {
    if (occupied.includes(rule.batterBase)) return null
    if (input.resultId === 'secondary-result.obstruction') {
      // 打者出塁時の既フォース連鎖はstateの単一advanceForが決める。
      for (const row of live)
        if (row.base === '1' && explicitBase(rule, '1') === 1n) return null
    }
  }
  if (input.resultId === 'secondary-result.obstruction') {
    const observed = ruling as Record<string, unknown>
    const obstructed = boundPerson(observed.obstructed, input.batterId, live)
    if (
      obstructed === null ||
      (!placed.includes(obstructed) &&
        !(observed.play_kind === 'no-play-on-obstructed-runner' &&
          targets.includes(obstructed)))
    ) return null
    if (
      observed.play_kind === 'play-on-obstructed-runner' &&
      obstructed !== 'batter' &&
      (explicitBase(rule, obstructed) === null ||
        (explicitBase(rule, obstructed) as bigint) <= BigInt(obstructed))
    ) return null
  }
  if (before.outs + outCount === 3n) {
    for (const row of live)
      if (explicitBase(rule, row.base) === 4n) return null
  }
  return rule
}

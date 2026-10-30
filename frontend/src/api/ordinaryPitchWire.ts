import type {
  SavedRuleWire,
  StateSnapshot,
  T1Value,
  T2NoEndCore,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import type { FirstBallObservations } from './firstBallWire'
import { canonicalUuid } from './authIntent'
import {
  isStartedGameStateSnapshot,
  isStartedGameStatFlags,
  isLegacyStartedT2,
} from './startedGame'

export type OrdinaryPrefixRef = Readonly<{
  version: '1'
  tenantId: string
  gameId: string
  generation: string
  length: string
}>
export type OrdinaryNoEnd = Readonly<{
  kind: 'evaluated-no-end-condition'
  scope: 'ordinary37'
  evaluation_point: 'post-play'
  basis: Readonly<{
    regulationInnings: string
    inning: string
    half: 'top' | 'bottom'
    halfCompleted: false
    coldBranches: readonly ('COLD-01' | 'COLD-04' | 'COLD-06')[]
    coldAggregate: 'COLD-07'
    drawBranch: 'DRAW-07' | 'DRAW-08'
    scoreUnchanged: true
    outsUnchanged: true
    priorOpen: true
    tiebreakActive: boolean
    configuredExtensionLimit: string | null
  }>
}>
export type OrdinaryResultId =
  | 'batting-result.ball'
  | 'batting-result.called-pitch'
  | 'batting-result.swinging-strike'
  | 'batting-result.foul'
export type OrdinaryContinuationRequest = Readonly<{
  version: '1'
  prefixRef: OrdinaryPrefixRef
  rules: SavedRuleWire
  t1: Readonly<{
    eventKind: 'batting-result'
    resultId: OrdinaryResultId
    pitchEventKind: 'pitch-event'
    before: StateSnapshot
  }>
  prior: Readonly<{
    kind: 'started-initial' | 'evaluated-prefix' | 'locked-prefix'
    prefixRef: OrdinaryPrefixRef
    rules: SavedRuleWire
    after: StateSnapshot
    t2: OrdinaryNoEnd | T2NoEndCore | null
  }>
}>
type CountEffect =
  Readonly<{ kind: 'unchanged' }> | Readonly<{ kind: 'delta'; value: '1' }>
type Advance = Readonly<{
  modality: 'hold' | 'not-applicable'
  destination: null
}>
export type OrdinaryT1Value = Readonly<
  Omit<T1Value, 'historyContext' | 'countEffect' | 'runnerDefaultAdvance'> & {
    countEffect: Readonly<{ strikes: CountEffect; balls: CountEffect }>
    runnerDefaultAdvance: Readonly<{
      first: Advance
      second: Advance
      third: Advance
    }>
  }
>
export type OrdinaryHistoryEntry = Readonly<{
  kind: 'confirmed-play'
  difference: Readonly<{
    stateFields: Partial<
      Record<
        'state.count.balls' | 'state.count.strikes',
        Readonly<{ before: string; after: string }>
      >
    >
    scoreboard: Readonly<Record<string, never>>
    statFlags: T1Value['statFlags']
  }>
}>
export type OrdinaryContinuationSuccess = Readonly<{
  ok: true
  value: Readonly<{
    t1: OrdinaryT1Value
    t2: OrdinaryNoEnd
    newHistoryEntry: OrdinaryHistoryEntry
    previousPrefixRef: OrdinaryPrefixRef
    nextPrefixRef: OrdinaryPrefixRef
  }>
}>
export type OrdinaryParticipants = Readonly<{
  batterId: string
  pitcherId: string
  catcherId: string
  battingOrder: string
}>
export type OrdinaryPitchPayload = Readonly<{
  formatVersion: 'ordinary-pitch-play-v1'
  observations: FirstBallObservations
  participants: OrdinaryParticipants
  calculation: Readonly<{
    formatVersion: 'ordinary-pitch-calculation-v1'
    artifactSha256: string
    request: OrdinaryContinuationRequest
    response: OrdinaryContinuationSuccess
  }>
}>
export type OrdinaryPreparedWire = Readonly<{
  payload: OrdinaryPitchPayload
  stateDiff: OrdinaryHistoryEntry['difference']
}>

/** 資格や原要求をログへ持ち出さない閉境界エラー。 */
export class OrdinaryPitchWireError extends Error {
  constructor() {
    super('通常投球の閉wireが成立しません')
    this.name = 'OrdinaryPitchWireError'
  }
}
function invalid(): never {
  throw new OrdinaryPitchWireError()
}
function exact(
  v: unknown,
  keys: readonly string[],
): v is Record<string, unknown> {
  return (
    typeof v === 'object' &&
    v !== null &&
    !Array.isArray(v) &&
    Object.keys(v).length === keys.length &&
    keys.every((k) => Object.hasOwn(v, k))
  )
}
function decimal(v: unknown): v is string {
  return (
    typeof v === 'string' && /^(?:0|[1-9][0-9]*)$/.test(v) && v.trim() === v
  )
}
function positive(v: unknown): v is string {
  return decimal(v) && BigInt(v) > 0n
}
function uuid(v: unknown): v is string {
  return typeof v === 'string' && v.length === 36 && canonicalUuid.test(v)
}
/** key順に依存せず、欠落/余剰も含めて完全に照合する。 */
export function sameOrdinaryWire(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (
    a === null ||
    b === null ||
    typeof a !== 'object' ||
    typeof b !== 'object'
  )
    return false
  if (Array.isArray(a) || Array.isArray(b))
    return (
      Array.isArray(a) &&
      Array.isArray(b) &&
      a.length === b.length &&
      a.every((v, i) => sameOrdinaryWire(v, b[i]))
    )
  const left = a as Record<string, unknown>,
    right = b as Record<string, unknown>
  return (
    Object.keys(left).length === Object.keys(right).length &&
    Object.keys(left).every(
      (k) => Object.hasOwn(right, k) && sameOrdinaryWire(left[k], right[k]),
    )
  )
}
export function isOrdinaryPrefixRef(v: unknown): v is OrdinaryPrefixRef {
  return (
    exact(v, ['version', 'tenantId', 'gameId', 'generation', 'length']) &&
    v.version === '1' &&
    uuid(v.tenantId) &&
    uuid(v.gameId) &&
    typeof v.generation === 'string' &&
    Array.from(v.generation).length > 0 &&
    Array.from(v.generation).length <= 128 &&
    decimal(v.length)
  )
}
export function isOrdinarySavedRules(v: unknown): v is SavedRuleWire {
  const ruleInt = (x: unknown) => positive(x) && BigInt(x) <= 99n
  return (
    exact(v, [
      'regulationInnings',
      'coldConditions',
      'extensionLimit',
      'tiebreak',
      'dh',
    ]) &&
    ruleInt(v.regulationInnings) &&
    typeof v.dh === 'boolean' &&
    (v.extensionLimit === null || ruleInt(v.extensionLimit)) &&
    Array.isArray(v.coldConditions) &&
    v.coldConditions.length <= 16 &&
    v.coldConditions.every(
      (c) =>
        exact(c, ['pointDifference', 'startInning']) &&
        ruleInt(c.pointDifference) &&
        ruleInt(c.startInning),
    ) &&
    (v.tiebreak === null ||
      (exact(v.tiebreak, ['startInning', 'runnerPlacement', 'leadoffRule']) &&
        ruleInt(v.tiebreak.startInning) &&
        typeof v.tiebreak.runnerPlacement === 'string' &&
        v.tiebreak.runnerPlacement.length > 0 &&
        typeof v.tiebreak.leadoffRule === 'string' &&
        v.tiebreak.leadoffRule.length > 0))
  )
}
export function isOrdinaryNoEnd(v: unknown): v is OrdinaryNoEnd {
  if (
    !exact(v, ['kind', 'scope', 'evaluation_point', 'basis']) ||
    v.kind !== 'evaluated-no-end-condition' ||
    v.scope !== 'ordinary37' ||
    v.evaluation_point !== 'post-play'
  )
    return false
  const b = v.basis
  return (
    exact(b, [
      'regulationInnings',
      'inning',
      'half',
      'halfCompleted',
      'coldBranches',
      'coldAggregate',
      'drawBranch',
      'scoreUnchanged',
      'outsUnchanged',
      'priorOpen',
      'tiebreakActive',
      'configuredExtensionLimit',
    ]) &&
    positive(b.regulationInnings) &&
    positive(b.inning) &&
    ['top', 'bottom'].includes(b.half as string) &&
    b.halfCompleted === false &&
    Array.isArray(b.coldBranches) &&
    b.coldBranches.length <= 16 &&
    b.coldBranches.every((c) =>
      ['COLD-01', 'COLD-04', 'COLD-06'].includes(c),
    ) &&
    b.coldAggregate === 'COLD-07' &&
    ['DRAW-07', 'DRAW-08'].includes(b.drawBranch as string) &&
    b.scoreUnchanged === true &&
    b.outsUnchanged === true &&
    b.priorOpen === true &&
    typeof b.tiebreakActive === 'boolean' &&
    (b.configuredExtensionLimit === null ||
      positive(b.configuredExtensionLimit))
  )
}
export function isOrdinaryContinuationRequest(
  v: unknown,
): v is OrdinaryContinuationRequest {
  if (
    !exact(v, ['version', 'prefixRef', 'rules', 't1', 'prior']) ||
    v.version !== '1' ||
    !isOrdinaryPrefixRef(v.prefixRef) ||
    !isOrdinarySavedRules(v.rules)
  )
    return false
  const t = v.t1,
    p = v.prior
  return (
    exact(t, ['eventKind', 'resultId', 'pitchEventKind', 'before']) &&
    t.eventKind === 'batting-result' &&
    [
      'batting-result.ball',
      'batting-result.called-pitch',
      'batting-result.swinging-strike',
      'batting-result.foul',
    ].includes(t.resultId as string) &&
    t.pitchEventKind === 'pitch-event' &&
    isStartedGameStateSnapshot(t.before) &&
    exact(p, ['kind', 'prefixRef', 'rules', 'after', 't2']) &&
    isOrdinaryPrefixRef(p.prefixRef) &&
    isOrdinarySavedRules(p.rules) &&
    isStartedGameStateSnapshot(p.after) &&
    (p.kind === 'evaluated-prefix'
      ? isOrdinaryNoEnd(p.t2) || isLegacyStartedT2(p.t2)
      : (p.kind === 'started-initial' || p.kind === 'locked-prefix') &&
        p.t2 === null)
  )
}
export function isOrdinaryHistoryEntry(v: unknown): v is OrdinaryHistoryEntry {
  if (
    !exact(v, ['kind', 'difference']) ||
    v.kind !== 'confirmed-play' ||
    !exact(v.difference, ['stateFields', 'scoreboard', 'statFlags'])
  )
    return false
  const f = v.difference.stateFields
  return (
    f !== null &&
    typeof f === 'object' &&
    !Array.isArray(f) &&
    Object.entries(f).every(
      ([k, p]) =>
        ['state.count.balls', 'state.count.strikes'].includes(k) &&
        exact(p, ['before', 'after']) &&
        decimal(p.before) &&
        decimal(p.after),
    ) &&
    exact(v.difference.scoreboard, []) &&
    isStartedGameStatFlags(v.difference.statFlags)
  )
}
export function isOrdinaryContinuationSuccess(
  v: unknown,
): v is OrdinaryContinuationSuccess {
  if (
    !exact(v, ['ok', 'value']) ||
    v.ok !== true ||
    !exact(v.value, [
      't1',
      't2',
      'newHistoryEntry',
      'previousPrefixRef',
      'nextPrefixRef',
    ])
  )
    return false
  const t = v.value.t1
  const count = (c: unknown) =>
    (exact(c, ['kind']) && c.kind === 'unchanged') ||
    (exact(c, ['kind', 'value']) && c.kind === 'delta' && c.value === '1')
  const advance = (a: unknown) =>
    exact(a, ['modality', 'destination']) &&
    ['hold', 'not-applicable'].includes(a.modality as string) &&
    a.destination === null
  return (
    exact(t, [
      'countEffect',
      'plateAppearanceEnded',
      'batterDestination',
      'runnerDefaultAdvance',
      'outEffect',
      'statFlags',
      'after',
    ]) &&
    exact(t.countEffect, ['strikes', 'balls']) &&
    count(t.countEffect.strikes) &&
    count(t.countEffect.balls) &&
    t.plateAppearanceEnded === false &&
    exact(t.batterDestination, ['kind']) &&
    t.batterDestination.kind === 'continue' &&
    exact(t.runnerDefaultAdvance, ['first', 'second', 'third']) &&
    Object.values(t.runnerDefaultAdvance).every(advance) &&
    exact(t.outEffect, ['count', 'targets']) &&
    t.outEffect.count === '0' &&
    Array.isArray(t.outEffect.targets) &&
    t.outEffect.targets.length === 0 &&
    isStartedGameStatFlags(t.statFlags) &&
    isStartedGameStateSnapshot(t.after) &&
    isOrdinaryNoEnd(v.value.t2) &&
    isOrdinaryHistoryEntry(v.value.newHistoryEntry) &&
    isOrdinaryPrefixRef(v.value.previousPrefixRef) &&
    isOrdinaryPrefixRef(v.value.nextPrefixRef)
  )
}
function observations(v: unknown): v is FirstBallObservations {
  if (
    !exact(v, [
      'pitchTypeKey',
      'course',
      'pitchSpeed',
      'stance',
      'battingSide',
    ]) ||
    typeof v.pitchTypeKey !== 'string' ||
    v.pitchTypeKey.length === 0 ||
    !exact(v.course, ['unit', 'x', 'y']) ||
    v.course.unit !== '1/263' ||
    ![v.course.x, v.course.y].every((x) => decimal(x) && BigInt(x) <= 263n)
  )
    return false
  const speed = v.pitchSpeed
  return (
    exact(speed, ['kmh', 'outsideRangeConfirmed']) &&
    typeof speed.outsideRangeConfirmed === 'boolean' &&
    (speed.kmh === null
      ? speed.outsideRangeConfirmed === false
      : typeof speed.kmh === 'string' &&
        /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(speed.kmh) &&
        speed.kmh.trim() === speed.kmh) &&
    (v.stance === null || (positive(v.stance) && BigInt(v.stance) <= 25n)) &&
    (v.battingSide === null || v.battingSide === '右' || v.battingSide === '左')
  )
}
/** 計算を行わず、正準要求/応答/今回差分をV7/V8へ写す。 */
export function formatOrdinaryPitchWire(
  request: OrdinaryContinuationRequest,
  computed: unknown,
  observation: FirstBallObservations,
  participants: OrdinaryParticipants,
): OrdinaryPreparedWire {
  if (
    !isOrdinaryContinuationRequest(request) ||
    !isOrdinaryContinuationSuccess(computed) ||
    !observations(observation) ||
    !exact(participants, [
      'batterId',
      'pitcherId',
      'catcherId',
      'battingOrder',
    ]) ||
    ![
      participants.batterId,
      participants.pitcherId,
      participants.catcherId,
    ].every(uuid) ||
    !/^[1-9]$/.test(participants.battingOrder)
  )
    return invalid()
  if (
    participants.battingOrder !==
    request.t1.before.stateFields['state.battingOrder']
  )
    return invalid()
  const before = request.prefixRef,
    next = computed.value.nextPrefixRef
  if (
    !sameOrdinaryWire(before, computed.value.previousPrefixRef) ||
    !sameOrdinaryWire({ ...before, length: next.length }, next) ||
    BigInt(next.length) !== BigInt(before.length) + 1n ||
    !sameOrdinaryWire(request.prior.prefixRef, before) ||
    !sameOrdinaryWire(request.prior.rules, request.rules) ||
    !sameOrdinaryWire(request.prior.after, request.t1.before) ||
    request.prior.kind === 'locked-prefix' ||
    !sameOrdinaryWire(
      computed.value.t1.statFlags,
      computed.value.newHistoryEntry.difference.statFlags,
    )
  )
    return invalid()
  return structuredClone({
    payload: {
      formatVersion: 'ordinary-pitch-play-v1',
      observations: observation,
      participants,
      calculation: {
        formatVersion: 'ordinary-pitch-calculation-v1',
        artifactSha256: artifactIdentity.sha256,
        request,
        response: computed,
      },
    },
    stateDiff: computed.value.newHistoryEntry.difference,
  })
}
/** 同一キーを維持し、再掲の高いD3は対象A5だけの確認へ使う。 */
export { readOrdinaryPitchAck } from './ordinaryPitchAck'

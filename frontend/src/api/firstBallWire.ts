import type {
  CombinedRequest,
  CombinedSuccess,
  T1Value,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import { parseD1AckEnvelope } from '../lib/sync/ackEnvelope'
import {
  CANON_ACK_STATE_RESULT,
  readCanonBoundaryResults,
} from '../lib/sync/canonOracle'
import type { AckResponse } from '../screens/GameScreenAckApplication'
import { canonicalUuid } from './authIntent'

export type FirstBallObservations = Readonly<{
  pitchTypeKey: string
  course: Readonly<{ unit: '1/263'; x: string; y: string }>
  pitchSpeed: Readonly<{ kmh: string | null; outsideRangeConfirmed: boolean }>
  stance: string | null
  battingSide: '右' | '左' | null
}>
export type FirstBallParticipants = Readonly<{
  batterId: string
  pitcherId: string
  catcherId: string
  battingOrder: '1'
}>
export type FirstBallPayload = Readonly<{
  formatVersion: 'first-ball-play-v1'
  observations: FirstBallObservations
  participants: FirstBallParticipants
  calculation: Readonly<{
    formatVersion: 'first-ball-calculation-v1'
    artifactSha256: string
    request: CombinedRequest
    response: CombinedSuccess
  }>
}>
export type FirstBallPreparedWire = Readonly<{
  payload: FirstBallPayload
  stateDiff: T1Value['historyContext'][0]['difference']
}>

/** 原値・資格を含めず、境界不成立だけを示す。 */
export class FirstBallWireError extends Error {
  constructor() {
    super('初球の閉wireが成立しません')
    this.name = 'FirstBallWireError'
  }
}
function invalid(): never {
  throw new FirstBallWireError()
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function exact(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  return (
    object(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  )
}
function integer(value: unknown): value is string {
  return typeof value === 'string' && /^(0|[1-9][0-9]*)$/.test(value)
}
function flags(value: unknown): boolean {
  const keys = [
    '投球回算入アウト',
    '投球数',
    '奪三振',
    '与四球',
    '与死球',
    '被安打',
    '被本塁打',
    '失点',
    '失策',
    '打席',
    '打数',
    '安打',
    '本塁打',
    '塁打',
    '犠打',
    '犠飛',
    '四球',
    '死球',
    '三振',
    '打撃妨害出塁',
    '走塁妨害出塁',
    '得点',
    '打点',
  ]
  return (
    exact(value, keys) && keys.every((key) => typeof value[key] === 'boolean')
  )
}
function score(value: unknown): boolean {
  return (
    exact(value, ['home', 'away']) && integer(value.home) && integer(value.away)
  )
}
function snapshot(value: unknown): boolean {
  if (!exact(value, ['stateFields', 'scoreboard'])) return false
  const s = value.stateFields,
    b = value.scoreboard
  return (
    exact(s, [
      'state.half',
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.runners',
      'state.battingOrder',
      'state.tiebreakActive',
      'state.gameEnded',
      'state.inning',
      'state.score',
    ]) &&
    ['top', 'bottom'].includes(s['state.half'] as string) &&
    [
      'empty',
      'first',
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
    ].includes(s['state.runners'] as string) &&
    [
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.battingOrder',
      'state.inning',
    ].every((k) => integer(s[k])) &&
    typeof s['state.tiebreakActive'] === 'boolean' &&
    typeof s['state.gameEnded'] === 'boolean' &&
    score(s['state.score']) &&
    exact(b, ['inningScores', 'hits', 'errors', 'strikeouts', 'walks']) &&
    score(b.inningScores) &&
    ['hits', 'errors', 'strikeouts', 'walks'].every((k) => integer(b[k]))
  )
}
function noEnd(value: unknown): boolean {
  if (
    !exact(value, ['kind', 'evaluation_point', 'basis']) ||
    value.kind !== 'evaluated-no-end-condition' ||
    value.evaluation_point !== 'post-play'
  )
    return false
  const b = value.basis
  if (!exact(b, ['regulation', 'cold', 'extra_and_draw', 'walk_off']))
    return false
  return (
    exact(b.regulation, [
      'kind',
      'regulation_innings',
      'observed_inning',
      'observed_half',
    ]) &&
    b.regulation.kind === 'before-regulation-completion' &&
    ['7', '9'].includes(b.regulation.regulation_innings as string) &&
    integer(b.regulation.observed_inning) &&
    ['top', 'bottom'].includes(b.regulation.observed_half as string) &&
    exact(b.cold, ['kind']) &&
    b.cold.kind === 'no-configured-cold-condition' &&
    exact(b.extra_and_draw, ['kind', 'configured_extension_limit']) &&
    b.extra_and_draw.kind === 'before-extra-inning-boundary' &&
    (b.extra_and_draw.configured_extension_limit === null ||
      integer(b.extra_and_draw.configured_extension_limit)) &&
    exact(b.walk_off, ['kind']) &&
    b.walk_off.kind === 'top-half-without-score-change'
  )
}
/** 同一artifactの応答を構造検証する。計算結果を補完・再計算しない。 */
function response(value: unknown): value is CombinedSuccess {
  if (
    !exact(value, ['ok', 'value']) ||
    value.ok !== true ||
    !exact(value.value, ['t1', 't2'])
  )
    return false
  const t = value.value.t1
  if (
    !exact(t, [
      'countEffect',
      'plateAppearanceEnded',
      'batterDestination',
      'runnerDefaultAdvance',
      'outEffect',
      'statFlags',
      'after',
      'historyContext',
    ])
  )
    return false
  if (
    !exact(t.countEffect, ['strikes', 'balls']) ||
    !exact(t.countEffect.strikes, ['kind']) ||
    t.countEffect.strikes.kind !== 'unchanged' ||
    !exact(t.countEffect.balls, ['kind', 'value']) ||
    t.countEffect.balls.kind !== 'delta' ||
    !integer(t.countEffect.balls.value) ||
    typeof t.plateAppearanceEnded !== 'boolean' ||
    !exact(t.batterDestination, ['kind']) ||
    t.batterDestination.kind !== 'continue'
  )
    return false
  if (
    !exact(t.runnerDefaultAdvance, ['first', 'second', 'third']) ||
    !['first', 'second', 'third'].every((k) => {
      const r = t.runnerDefaultAdvance as Record<string, unknown>
      const v = r[k]
      return (
        exact(v, ['modality', 'destination']) &&
        v.modality === 'not-applicable' &&
        v.destination === null
      )
    })
  )
    return false
  if (
    !exact(t.outEffect, ['count', 'targets']) ||
    !integer(t.outEffect.count) ||
    !Array.isArray(t.outEffect.targets) ||
    t.outEffect.targets.length !== 0 ||
    !flags(t.statFlags) ||
    !snapshot(t.after) ||
    !Array.isArray(t.historyContext) ||
    t.historyContext.length !== 1
  )
    return false
  const h = t.historyContext[0]
  if (
    !exact(h, ['kind', 'difference']) ||
    h.kind !== 'confirmed-play' ||
    !exact(h.difference, ['stateFields', 'scoreboard', 'statFlags']) ||
    !exact(h.difference.stateFields, ['state.count.balls']) ||
    !exact(h.difference.scoreboard, []) ||
    !flags(h.difference.statFlags)
  )
    return false
  const pair = h.difference.stateFields['state.count.balls']
  return (
    exact(pair, ['before', 'after']) &&
    integer(pair.before) &&
    integer(pair.after) &&
    noEnd(value.value.t2)
  )
}

/** 計算の原request/response・観測・名簿をV7/V8へ無計算で写す。 */
export function formatFirstBallWire(
  request: CombinedRequest,
  computed: unknown,
  observations: FirstBallObservations,
  participants: FirstBallParticipants,
): FirstBallPreparedWire {
  if (
    !exact(request, ['t1', 'rules']) ||
    !exact(request.t1, ['eventKind', 'resultId', 'pitchEventKind', 'before']) ||
    !exact(request.rules, [
      'regulationInnings',
      'coldConditions',
      'extensionLimit',
      'tiebreak',
      'dh',
    ]) ||
    !integer(request.rules.regulationInnings) ||
    typeof request.rules.dh !== 'boolean' ||
    !(
      request.rules.extensionLimit === null ||
      integer(request.rules.extensionLimit)
    ) ||
    !Array.isArray(request.rules.coldConditions) ||
    !request.rules.coldConditions.every(
      (c) =>
        exact(c, ['pointDifference', 'startInning']) &&
        integer(c.pointDifference) &&
        integer(c.startInning),
    ) ||
    !(
      request.rules.tiebreak === null ||
      (exact(request.rules.tiebreak, [
        'startInning',
        'runnerPlacement',
        'leadoffRule',
      ]) &&
        integer(request.rules.tiebreak.startInning) &&
        typeof request.rules.tiebreak.runnerPlacement === 'string' &&
        typeof request.rules.tiebreak.leadoffRule === 'string')
    ) ||
    request.t1.eventKind !== 'batting-result' ||
    request.t1.resultId !== 'batting-result.ball' ||
    request.t1.pitchEventKind !== 'pitch-event' ||
    !snapshot(request.t1.before) ||
    !response(computed)
  )
    return invalid()
  if (
    !exact(observations, [
      'pitchTypeKey',
      'course',
      'pitchSpeed',
      'stance',
      'battingSide',
    ]) ||
    typeof observations.pitchTypeKey !== 'string' ||
    observations.pitchTypeKey.length === 0 ||
    !exact(observations.course, ['unit', 'x', 'y']) ||
    observations.course.unit !== '1/263' ||
    ![observations.course.x, observations.course.y].every(
      (v) => integer(v) && BigInt(v) <= 263n,
    )
  )
    return invalid()
  if (
    !exact(observations.pitchSpeed, ['kmh', 'outsideRangeConfirmed']) ||
    typeof observations.pitchSpeed.outsideRangeConfirmed !== 'boolean' ||
    (observations.pitchSpeed.kmh === null
      ? observations.pitchSpeed.outsideRangeConfirmed
      : typeof observations.pitchSpeed.kmh !== 'string' ||
        !/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(observations.pitchSpeed.kmh))
  )
    return invalid()
  if (
    (observations.stance !== null &&
      (!integer(observations.stance) ||
        BigInt(observations.stance) < 1n ||
        BigInt(observations.stance) > 25n)) ||
    (observations.battingSide !== null &&
      observations.battingSide !== '右' &&
      observations.battingSide !== '左')
  )
    return invalid()
  if (
    !exact(participants, [
      'batterId',
      'pitcherId',
      'catcherId',
      'battingOrder',
    ]) ||
    participants.battingOrder !== '1' ||
    ![
      participants.batterId,
      participants.pitcherId,
      participants.catcherId,
    ].every(
      (v) => typeof v === 'string' && v.length === 36 && canonicalUuid.test(v),
    )
  )
    return invalid()
  const payload: FirstBallPayload = {
    formatVersion: 'first-ball-play-v1',
    observations,
    participants,
    calculation: {
      formatVersion: 'first-ball-calculation-v1',
      artifactSha256: artifactIdentity.sha256,
      request,
      response: computed,
    },
  }
  return structuredClone({
    payload,
    stateDiff: computed.value.t1.historyContext[0].difference,
  })
}

/** 正規の単一受理ACKだけを既adapterへ渡す。未対応拒否は成功へ補完しない。 */
export function readFirstBallAck(
  value: unknown,
  key: Readonly<{ d4: string; d1: number; d5: string }>,
): AckResponse | undefined {
  try {
    const envelope = parseD1AckEnvelope(value)
    if (envelope.eventResults.length !== 1 || envelope.advancedD3 !== key.d1)
      return undefined
    const item = envelope.eventResults[0]!
    if (
      item.d4 !== key.d4 ||
      item.d1 !== key.d1 ||
      item.d5 !== key.d5 ||
      item.a5Result.id !== CANON_ACK_STATE_RESULT.ACCEPTED
    )
      return undefined
    const terminal = readCanonBoundaryResults().find(
      (row) => row.name === '要求終端',
    )
    if (!terminal) return undefined
    return { envelope: value, boundaryResult: terminal.id }
  } catch {
    return undefined
  }
}

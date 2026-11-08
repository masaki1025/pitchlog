import {
  isRunnerRequest,
  isRunnerSuccess,
  formatRunnerEventWire,
} from './runnerEventWire'
import type { RunnerRequest, RunnerSuccess, RunnerV7 } from './runnerEventWire'
import schema from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type {
  LineupPlayPrefixV7,
  LineupPlayPrefixV8,
  BattedHitObservations,
  IntentionalWalkPlayPrefixV7,
} from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import type {
  Observations,
  Participants,
} from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import type { RunnerAdvanceOverridesByRunner } from './runnerAdvanceWire'
import { lineupPrefixSpikeSchema } from './lineupPrefixSpikeSchema'
import identity from '../../public/domain/pitchlog-domain.json'
import {
  isClosedPlaySchema,
  observationsValid,
  playHash,
} from './terminalPitchWire'
import { sameOrdinaryWire } from './ordinaryPitchWire'

export type BattedOfficialScoring =
  | BattedHitObservations['officialScoringPayload']
  | {
      kind: 'error-recorded'
      errors: [
        {
          fielder: { kind: 'official'; player_id: string }
          count: 1
        },
      ]
    }
export type BattedHitWireObservations = Omit<
  BattedHitObservations,
  'runnerAdvanceOverridesByRunner' | 'officialScoringPayload'
> & {
  runnerAdvanceOverridesByRunner: RunnerAdvanceOverridesByRunner
  officialScoringPayload: BattedOfficialScoring
  rbiRulingByRunner?: Partial<
    Record<
      '1' | '2' | '3',
      'ordinary-play' | 'kept-running' | 'stopped-and-restarted'
    >
  >
}
export type BattedOtherResult =
  | 'batting-result.batted-reach'
  | 'batting-result.error'
  | 'batting-result.fielders-choice'
  | 'batting-result.sacrifice-bunt'
  | 'batting-result.sacrifice-fly'
  | 'batting-result.sacrifice-bunt-error'
export type BattedOtherWireObservations = Omit<
  BattedHitWireObservations,
  'resultId'
> & { resultId: BattedOtherResult }
export type BattedDoublePlayWireObservations = Omit<
  BattedHitWireObservations,
  'resultId'
> & {
  resultId: 'batting-result.double-play'
  outRunner: { base: '1'; runnerId: string; outKind: 'force-out' }
}
export type BattedOutWireObservations = Omit<
  BattedHitWireObservations,
  'resultId' | 'thirdOutObservation'
> & {
  resultId: 'batting-result.batted-out'
  thirdOutObservation:
    | { kind: 'none' }
    | {
        kind: 'batter-before-first'
        batter: { kind: 'official'; player_id: string }
      }
}
type IntentionalWalkObservation = IntentionalWalkPlayPrefixV7['observations']

export function isLineupDefinition<T>(
  value: unknown,
  name: string,
): value is T {
  return isClosedPlaySchema<T>(value, schema, name)
}

/** spike候補の明示進塁を、原値のまま拡張schemaで厳格に検証する。 */
export function isLineupSpikeDefinition<T>(
  value: unknown,
  name: string,
): value is T {
  return isClosedPlaySchema<T>(value, lineupPrefixSpikeSchema, name)
}
/** 自己echo二欄以外の正式32fieldを保存側と同じ形で束縛する。 */
export function lineupWireHead(
  q: Request | RunnerRequest,
  response: Success | RunnerSuccess,
) {
  if (
    !isLineupSpikeDefinition<Request | RunnerRequest>(q, 'Request') ||
    !isLineupSpikeDefinition<Success | RunnerSuccess>(response, 'Success')
  )
    throw new Error('打席の要求・応答を確認できません')
  const v = response.value,
    n = v.nextPrefixRef,
    s = q.source
  if (
    !sameOrdinaryWire(v.previousPrefixRef, q.prefixRef) ||
    !sameOrdinaryWire(v.playIdentity, q.playIdentity) ||
    !sameOrdinaryWire(v.sourcePosition, s.position) ||
    !sameOrdinaryWire(v.beforeParticipants, s.participants) ||
    !sameOrdinaryWire(v.responsibility, s.responsibility) ||
    n.checkpoint.id !== q.nextCheckpoint.id ||
    n.checkpoint.revision !== q.nextCheckpoint.revision ||
    v.executionArtifactSha256 !== s.executionArtifactSha256
  )
    throw new Error('打席の実応答を確認できません')
  const head = {
    formatVersion: 'play-prefix-wire-head-v3',
    version: n.version,
    scope: n.scope,
    tenantId: n.tenantId,
    gameId: n.gameId,
    generation: n.generation,
    length: n.length,
    checkpointId: n.checkpoint.id,
    checkpointRevision: n.checkpoint.revision,
    historyVersion: n.historyVersion,
    origin: n.origin,
    previousPrefixRef: v.previousPrefixRef,
    rules: q.rules,
    rulesDigest: s.rulesDigest,
    layoutDigest: s.layoutDigest,
    rosterDigest: v.rosterDigest,
    lineup: v.lineup,
    priorArtifactSha256: s.priorArtifactSha256,
    executionArtifactSha256: v.executionArtifactSha256,
    sourcePosition: v.sourcePosition,
    source: s,
    sourceProvenance: s.provenance,
    playIdentity: v.playIdentity,
    responsibility: v.responsibility,
    nextResponsibility: v.nextResponsibility,
    before: q.t1.before,
    T1: v.t1,
    T2: v.t2,
    newHistoryEntry: v.newHistoryEntry,
    runners: v.runners,
    beforeParticipants: v.beforeParticipants,
    participants: v.participants,
  }
  if ('runnerObservation' in q.t1) {
    if (!('runnerScoreEffects' in v))
      throw new Error('走者計算の算入根拠を確認できません')
    return {
      ...head,
      runnerObservation: q.t1.runnerObservation,
      runnerScoreEffects: v.runnerScoreEffects,
    }
  }
  if ('rbiRulingByRunner' in q.t1) {
    if (!('runnerScoreEffects' in v) || v.runnerScoreEffects.length === 0)
      throw new Error('打球の算入根拠を確認できません')
    return {
      ...head,
      rbiRulingByRunner: q.t1.rbiRulingByRunner,
      runnerScoreEffects: v.runnerScoreEffects,
    }
  }
  if ('runnerScoreEffects' in v) {
    if (
      !['batting-result.batted-out', 'batting-result.sacrifice-bunt'].includes(
        q.t1.resultId,
      ) ||
      !('runnerAdvanceOverrides' in q.t1) ||
      typeof q.t1.runnerAdvanceOverrides !== 'object' ||
      q.t1.runnerAdvanceOverrides.kind !== 'applied' ||
      q.t1.runnerAdvanceOverrides.overrides.length === 0 ||
      v.runnerScoreEffects.length !== 0 ||
      v.t1.statFlags['得点'] !== false ||
      v.t1.statFlags['打点'] !== false ||
      v.t1.statFlags['失点'] !== false ||
      !sameOrdinaryWire(
        q.t1.before.stateFields['state.score'],
        v.t1.after.stateFields['state.score'],
      )
    )
      throw new Error('旧入力に走者計算を混在できません')
    return { ...head, runnerScoreEffects: v.runnerScoreEffects }
  }
  return head
}
export async function sealLineupMetadata<
  Q extends Request | RunnerRequest,
  R extends Success | RunnerSuccess,
>(request: Q, response: R) {
  const digest = await playHash(lineupWireHead(request, response))
  return {
    request: Object.assign(structuredClone(request), {
      nextCheckpoint: { ...request.nextCheckpoint, digest },
    }),
    response: Object.assign(structuredClone(response), {
      value: Object.assign(structuredClone(response.value), {
        nextPrefixRef: {
          ...response.value.nextPrefixRef,
          checkpoint: { ...response.value.nextPrefixRef.checkpoint, digest },
        },
      }),
    }),
  }
}
export async function formatLineupPrefixWire(
  request: Request,
  response: Success,
  observations:
    | Observations
    | BattedHitObservations
    | BattedHitWireObservations
    | BattedOtherWireObservations
    | BattedDoublePlayWireObservations
    | BattedOutWireObservations
    | IntentionalWalkObservation
    | RunnerV7['observations'],
  participants: Participants,
): Promise<{ payload: LineupPlayPrefixV7; stateDiff: LineupPlayPrefixV8 }> {
  if ('runnerObservation' in observations) {
    if (!isRunnerRequest(request) || !isRunnerSuccess(response))
      throw new Error('走者操作の要求・実応答が不一致です')
    return formatRunnerEventWire(request, response, observations, participants)
  }
  const digest = await playHash(lineupWireHead(request, response))
  const payload = {
    formatVersion: 'play-prefix-play-v3',
    observations,
    participants,
    calculation: {
      formatVersion: 'play-prefix-calculation-v3',
      artifactSha256: identity.sha256,
      request,
      response,
    },
  }
  const nonpitch =
    'kind' in observations && observations.kind === 'intentional-walk'
  const pitchObservations = 'kind' in observations ? null : observations
  if (
    !isClosedPlaySchema<LineupPlayPrefixV7>(payload, lineupPrefixSpikeSchema) ||
    (nonpitch &&
      (request.t1.resultId !== 'batting-result.intentional-walk' ||
        request.t1.pitchEventKind !== 'non-pitch-event')) ||
    (pitchObservations !== null &&
      !observationsValid({
        pitchTypeKey: pitchObservations.pitchTypeKey,
        course: pitchObservations.course,
        pitchSpeed: pitchObservations.pitchSpeed,
        stance: pitchObservations.stance,
        battingSide: pitchObservations.battingSide,
      })) ||
    ('battedBall' in observations &&
      [observations.battedBall.hitX, observations.battedBall.hitY].some(
        (value) =>
          value !== null &&
          !/^(?:0(?:\.[0-9]+)?|1(?:\.0+)?|-0(?:\.0+)?)$/.test(value),
      )) ||
    request.nextCheckpoint.digest !== digest ||
    response.value.nextPrefixRef.checkpoint.digest !== digest ||
    request.source.executionArtifactSha256 !== identity.sha256 ||
    !sameOrdinaryWire(
      {
        batterId: participants.batterId,
        pitcherId: participants.pitcherId,
        catcherId: participants.catcherId,
        battingOrder: participants.battingOrder,
      },
      request.source.participants,
    )
  )
    throw new Error('打席の保存値を確認できません')
  return structuredClone({
    payload: payload as unknown as LineupPlayPrefixV7,
    stateDiff: response.value.newHistoryEntry.difference,
  })
}

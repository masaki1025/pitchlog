import schema from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import type {
  Request,
  Success,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type {
  LineupPlayPrefixV7,
  LineupPlayPrefixV8,
  BattedHitObservations,
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

type BattedHitWireObservations = Omit<
  BattedHitObservations,
  'runnerAdvanceOverridesByRunner'
> & { runnerAdvanceOverridesByRunner: RunnerAdvanceOverridesByRunner }

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
export function lineupWireHead(q: Request, response: Success) {
  if (
    !isLineupSpikeDefinition<Request>(q, 'Request') ||
    !isLineupSpikeDefinition<Success>(response, 'Success')
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
  return {
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
}
export async function sealLineupMetadata(request: Request, response: Success) {
  const digest = await playHash(lineupWireHead(request, response))
  return {
    request: {
      ...structuredClone(request),
      nextCheckpoint: { ...request.nextCheckpoint, digest },
    },
    response: {
      ok: true as const,
      value: {
        ...structuredClone(response.value),
        nextPrefixRef: {
          ...response.value.nextPrefixRef,
          checkpoint: { ...response.value.nextPrefixRef.checkpoint, digest },
        },
      },
    },
  }
}
export async function formatLineupPrefixWire(
  request: Request,
  response: Success,
  observations:
    Observations | BattedHitObservations | BattedHitWireObservations,
  participants: Participants,
): Promise<{ payload: LineupPlayPrefixV7; stateDiff: LineupPlayPrefixV8 }> {
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
  if (
    !isClosedPlaySchema<LineupPlayPrefixV7>(payload, lineupPrefixSpikeSchema) ||
    !observationsValid({
      pitchTypeKey: observations.pitchTypeKey,
      course: observations.course,
      pitchSpeed: observations.pitchSpeed,
      stance: observations.stance,
      battingSide: observations.battingSide,
    }) ||
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

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

function appliedOverrides(value: unknown): boolean {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as Record<string, unknown>).kind === 'applied'
  )
}

function occupied(
  runners: unknown,
  slot: 'first' | 'second' | 'third',
): boolean {
  if (runners === 'loaded') return true
  if (slot === 'first')
    return (
      runners === 'first' ||
      runners === 'first-second' ||
      runners === 'first-third'
    )
  if (slot === 'second')
    return (
      runners === 'second' ||
      runners === 'first-second' ||
      runners === 'second-third'
    )
  return (
    runners === 'third' ||
    runners === 'first-third' ||
    runners === 'second-third'
  )
}

type ValidationRequest = {
  t1: { runnerAdvanceOverrides?: unknown }
}
type ValidationResponse = {
  value: { t1: { runnerDefaultAdvance: Record<string, unknown> } }
}
type ValidationPayload = {
  observations: { runnerAdvanceOverridesByRunner?: unknown }
  calculation: {
    request: {
      t1: {
        runnerAdvanceOverrides?: unknown
        before: { stateFields: Record<string, unknown> }
      }
    }
    response: ValidationResponse
  }
}

/** 正準schemaが未受理の明示進塁だけを既存形へ戻し、他の全fieldを同じ検査へ通す。 */
function requestForValidation(request: Request): Request {
  const t1 = request.t1 as unknown as ValidationRequest['t1']
  if (!appliedOverrides(t1.runnerAdvanceOverrides)) return request
  const copy = structuredClone(request) as unknown as ValidationRequest
  copy.t1.runnerAdvanceOverrides = 'not-applied'
  return copy as unknown as Request
}

function responseForValidation(response: Success, request: Request): Success {
  const requestT1 =
    request.t1 as unknown as ValidationPayload['calculation']['request']['t1']
  if (!appliedOverrides(requestT1.runnerAdvanceOverrides)) return response
  const copy = structuredClone(response) as unknown as ValidationResponse
  const runners = requestT1.before.stateFields['state.runners']
  for (const slot of ['first', 'second', 'third'] as const)
    copy.value.t1.runnerDefaultAdvance[slot] = occupied(runners, slot)
      ? { modality: 'hold', destination: null }
      : { modality: 'not-applicable', destination: null }
  return copy as unknown as Success
}

function payloadForValidation(payload: unknown): unknown {
  const value = payload as ValidationPayload
  if (!appliedOverrides(value.observations.runnerAdvanceOverridesByRunner))
    return payload
  const copy = structuredClone(value)
  copy.observations.runnerAdvanceOverridesByRunner = {
    kind: 'not-applied',
    overrides: [],
  }
  copy.calculation.request.t1.runnerAdvanceOverrides = 'not-applied'
  const runners =
    copy.calculation.request.t1.before.stateFields['state.runners']
  for (const slot of ['first', 'second', 'third'] as const)
    copy.calculation.response.value.t1.runnerDefaultAdvance[slot] = occupied(
      runners,
      slot,
    )
      ? { modality: 'hold', destination: null }
      : { modality: 'not-applicable', destination: null }
  return copy
}
/** 自己echo二欄以外の正式32fieldを保存側と同じ形で束縛する。 */
export function lineupWireHead(q: Request, response: Success) {
  if (
    !isLineupDefinition<Request>(requestForValidation(q), 'Request') ||
    !isLineupDefinition<Success>(responseForValidation(response, q), 'Success')
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
    !isClosedPlaySchema<LineupPlayPrefixV7>(
      payloadForValidation(payload),
      schema,
    ) ||
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

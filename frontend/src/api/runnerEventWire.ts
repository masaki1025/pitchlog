import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import schema from '../../../contracts/state-transition/lineup_play_prefix_payload_schema_v1.json'
import type {
  RunnerObservation as FormalRunnerObservation,
  RunnerPerPitch as FormalRunnerPerPitch,
} from '../../../contracts/state-transition/lineup_play_prefix_v1'
import type { RunnerNormalPlayPrefixV7 } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import type { Participants } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import { isClosedPlaySchema, playHash } from './terminalPitchWire'
import { lineupWireHead } from './lineupPrefixWire'
import { sameOrdinaryWire } from './ordinaryPitchWire'

/** root固定de3bの正式候補型を再利用する。旧型へのcast/原値補修はしない。 */
export type RunnerPerPitch = FormalRunnerPerPitch
export type RunnerObservationWire = FormalRunnerObservation
export type RunnerV7 = RunnerNormalPlayPrefixV7
export type RunnerRequest = RunnerV7['calculation']['request']
export type RunnerSuccess = RunnerV7['calculation']['response']
export type RunnerValue = RunnerSuccess['value']
export type RunnerT1Value = RunnerValue['t1']
export function isRunnerObservation(
  value: unknown,
): value is RunnerObservationWire {
  return isClosedPlaySchema<RunnerObservationWire>(
    value,
    schema,
    'RunnerObservation',
  )
}

/** 未供給の正式schemaでは閉拒否する。旧schema向けの原値補修は行わない。 */
export function isRunnerRequest(value: unknown): value is RunnerRequest {
  return (
    isClosedPlaySchema<RunnerRequest>(value, schema, 'Request') &&
    typeof value === 'object' &&
    value !== null &&
    't1' in value &&
    typeof value.t1 === 'object' &&
    value.t1 !== null &&
    'runnerObservation' in value.t1
  )
}
export function isRunnerSuccess(value: unknown): value is RunnerSuccess {
  return (
    isClosedPlaySchema<RunnerSuccess>(value, schema, 'Success') &&
    typeof value === 'object' &&
    value !== null &&
    'value' in value &&
    typeof value.value === 'object' &&
    value.value !== null &&
    'runnerScoreEffects' in value.value
  )
}
export async function formatRunnerEventWire(
  request: RunnerRequest,
  response: RunnerSuccess,
  observations: RunnerV7['observations'],
  participants: Participants,
) {
  if (
    request.source.executionArtifactSha256 !== artifactIdentity.sha256 ||
    response.value.executionArtifactSha256 !== artifactIdentity.sha256
  )
    throw new Error('走者計算と実artifactの版が一致しません')
  if (
    !sameOrdinaryWire(
      observations.runnerObservation,
      request.t1.runnerObservation,
    ) ||
    !sameOrdinaryWire(participants, response.value.beforeParticipants)
  )
    throw new Error('走者操作の原観測・参加者が不一致です')
  const digest = await playHash(lineupWireHead(request, response))
  if (
    request.nextCheckpoint.digest !== digest ||
    response.value.nextPrefixRef.checkpoint.digest !== digest
  )
    throw new Error('走者操作の固定封印が不一致です')
  const payload = {
    formatVersion: 'play-prefix-play-v3',
    observations: structuredClone(observations),
    participants: structuredClone(participants),
    calculation: {
      formatVersion: 'play-prefix-calculation-v3',
      artifactSha256: response.value.executionArtifactSha256,
      request,
      response,
    },
  }
  if (!isClosedPlaySchema<RunnerV7>(payload, schema))
    throw new Error('走者操作の正式入力形式が未供給か不一致です')
  return {
    payload,
    stateDiff: structuredClone(response.value.newHistoryEntry.difference),
  }
}

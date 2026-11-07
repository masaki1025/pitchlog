/** 実P3の対象版と独立応答だけを閉検証する。野球計算は行わない。 */
import type { PrefixRef } from '../../../contracts/state-transition/lineup_play_prefix_v1'
import { apiRequest, type SyncRequestCredentials } from './client'
import { postRecoverableP3Change } from './recoverableSyncPost'
import { canonicalUuid } from './authIntent'
import { isLineupDefinition } from './lineupPrefixWire'
import { sameOrdinaryWire } from './ordinaryPitchWire'
import type { FirstBallObservations } from './firstBallWire'

export type P3OriginalResult =
  | 'batting-result.ball'
  | 'batting-result.called-pitch'
  | 'batting-result.called-strikeout'
export type P3ReplacementResult =
  'batting-result.ball' | 'batting-result.called-pitch'

export type P3TargetOffer = Readonly<{
  target_reference: Readonly<{ game: string; d4: string; d1: number }>
  expected_version: 1
  expected_prefix_ref: PrefixRef
  target_event_id: string
  target_play_id: string
  original_result_id: P3OriginalResult
}>

export type P3ChangeConfirmation = Readonly<{
  target_reference: P3TargetOffer['target_reference']
  confirmed_version: 2
  d5: string
  source_event_id: string
  target_play_id: string
  stats_version_id: string
  current_prefix_ref: PrefixRef
  current_after: unknown
}>

export type P3ChangeBody = Readonly<{
  recovery_generation: string
  recording_right_proof: string
  change: Readonly<{
    d5: string
    game_id: string
    event_kind: 'play_change'
    target_reference: P3TargetOffer['target_reference']
    expected_version: 1
    payload: Readonly<{
      formatVersion: 'p3-lineup-pitch-change-v1'
      expectedPrefixRef: PrefixRef
      targetEventId: string
      targetPlayId: string
      originalResultId: P3OriginalResult
      replacementResultId: P3ReplacementResult
      replacementObservations: FirstBallObservations
    }>
  }>
}>

export type P3ProductResult =
  | Readonly<{
      kind: 'accepted'
      targetReference: Readonly<{
        試合: string
        '対象の D4': string
        '対象の D1': number
      }>
      expectedVersion: 1
      d5: string
      confirmedContent: P3ChangeBody['change']['payload']
      acceptedAt: string
    }>
  | Readonly<{
      kind: 'rejected'
      boundary: 'B8' | 'B9' | 'B10' | 'B11' | 'B12' | 'B13' | 'B14'
      d5: string
    }>

const record = (v: unknown): v is Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v)
const exact = (v: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(v).sort().join(',') === [...keys].sort().join(',')
const uuid = (v: unknown): v is string =>
  typeof v === 'string' && canonicalUuid.test(v)
const positive = (v: unknown): v is number =>
  typeof v === 'number' && Number.isSafeInteger(v) && v > 0

function parseOffer(value: unknown, gameId: string, d1: number): P3TargetOffer {
  if (
    !record(value) ||
    !exact(value, [
      'target_reference',
      'expected_version',
      'expected_prefix_ref',
      'target_event_id',
      'target_play_id',
      'original_result_id',
    ]) ||
    !record(value.target_reference) ||
    !exact(value.target_reference, ['game', 'd4', 'd1']) ||
    value.target_reference.game !== gameId ||
    value.target_reference.d1 !== d1 ||
    typeof value.target_reference.d4 !== 'string' ||
    !/^d4\.1\.[A-Za-z0-9_-]{55}$/.test(value.target_reference.d4) ||
    value.expected_version !== 1 ||
    !isLineupDefinition<PrefixRef>(value.expected_prefix_ref, 'PrefixRef') ||
    value.expected_prefix_ref.gameId !== gameId ||
    value.expected_prefix_ref.generation !== value.target_reference.d4 ||
    !uuid(value.target_event_id) ||
    !uuid(value.target_play_id) ||
    ![
      'batting-result.ball',
      'batting-result.called-pitch',
      'batting-result.called-strikeout',
    ].includes(String(value.original_result_id))
  )
    throw new Error('P3対象版の真正読取が不一致です')
  return value as P3TargetOffer
}

/** GETは保存資格ではない。送信時にもE1と対象版を再照合する。 */
export async function readP3TargetOffer(
  gameId: string,
  d1: number,
  signal?: AbortSignal,
): Promise<P3TargetOffer> {
  if (!uuid(gameId) || !positive(d1) || d1 > 25)
    throw new Error('P3対象位置が不正です')
  const raw = await apiRequest<unknown>(
    'GET',
    `/games/${gameId}/sync/change-target/${d1}`,
    { tenantBound: true, signal },
  )
  return parseOffer(raw, gameId, d1)
}

/** 受理D5と実slot版を同read TXの現headへ束縛した確認だけを読む。 */
export async function readP3ChangeConfirmation(
  gameId: string,
  d1: number,
  d5: string,
  signal?: AbortSignal,
): Promise<P3ChangeConfirmation> {
  if (!uuid(gameId) || !positive(d1) || d1 > 25 || !uuid(d5))
    throw new Error('P3確認条件が不正です')
  const value = await apiRequest<unknown>(
    'GET',
    `/games/${gameId}/sync/change-confirmation/${d1}`,
    { tenantBound: true, signal },
  )
  if (
    !record(value) ||
    !exact(value, [
      'target_reference',
      'confirmed_version',
      'd5',
      'source_event_id',
      'target_play_id',
      'stats_version_id',
      'current_prefix_ref',
      'current_after',
    ]) ||
    !record(value.target_reference) ||
    !exact(value.target_reference, ['game', 'd4', 'd1']) ||
    value.target_reference.game !== gameId ||
    value.target_reference.d1 !== d1 ||
    typeof value.target_reference.d4 !== 'string' ||
    !/^d4\.1\.[A-Za-z0-9_-]{55}$/.test(value.target_reference.d4) ||
    value.confirmed_version !== 2 ||
    value.d5 !== d5 ||
    !uuid(value.source_event_id) ||
    !uuid(value.target_play_id) ||
    !uuid(value.stats_version_id) ||
    !isLineupDefinition<PrefixRef>(value.current_prefix_ref, 'PrefixRef') ||
    !record(value.current_after) ||
    value.current_prefix_ref.tenantId === '' ||
    value.current_prefix_ref.gameId !== gameId ||
    value.current_prefix_ref.generation !== value.target_reference.d4
  )
    throw new Error('P3受理版の真正読取が不一致です')
  return value as P3ChangeConfirmation
}

export function p3ChangeBody(
  offer: P3TargetOffer,
  d5: string,
  recoveryGeneration: string,
  recordingRightProof: string,
  replacementResultId: P3ReplacementResult,
  observations: FirstBallObservations,
): P3ChangeBody {
  if (
    !uuid(d5) ||
    !/^[1-9][0-9]*$/.test(recoveryGeneration) ||
    !recordingRightProof ||
    !['batting-result.ball', 'batting-result.called-pitch'].includes(
      replacementResultId,
    ) ||
    !record(observations) ||
    !exact(observations, [
      'pitchTypeKey',
      'course',
      'pitchSpeed',
      'stance',
      'battingSide',
    ])
  )
    throw new Error('P3変更の明示本文が不正です')
  return {
    recovery_generation: recoveryGeneration,
    recording_right_proof: recordingRightProof,
    change: {
      d5,
      game_id: offer.target_reference.game,
      event_kind: 'play_change',
      target_reference: offer.target_reference,
      expected_version: offer.expected_version,
      payload: {
        formatVersion: 'p3-lineup-pitch-change-v1',
        expectedPrefixRef: offer.expected_prefix_ref,
        targetEventId: offer.target_event_id,
        targetPlayId: offer.target_play_id,
        originalResultId: offer.original_result_id,
        replacementResultId,
        replacementObservations: observations,
      },
    },
  }
}

function parseResult(raw: unknown, body: P3ChangeBody): P3ProductResult {
  if (!record(raw) || raw.d5 !== body.change.d5)
    throw new Error('P3応答のD5が一致しません')
  if (raw.boundary === '変更受理') {
    const target = raw.target_reference
    if (
      !exact(raw, [
        'boundary',
        'target_reference',
        'expected_version',
        'd5',
        'confirmed_content',
        'accepted_at',
      ]) ||
      !record(target) ||
      !exact(target, ['試合', '対象の D4', '対象の D1']) ||
      target['試合'] !== body.change.target_reference.game ||
      target['対象の D4'] !== body.change.target_reference.d4 ||
      target['対象の D1'] !== body.change.target_reference.d1 ||
      raw.expected_version !== body.change.expected_version ||
      !sameOrdinaryWire(raw.confirmed_content, body.change.payload) ||
      typeof raw.accepted_at !== 'string' ||
      !/^\d{4}-\d\d-\d\dT/.test(raw.accepted_at)
    )
      throw new Error('P3受理結果のI6全組が一致しません')
    return {
      kind: 'accepted',
      targetReference: target as Extract<
        P3ProductResult,
        { kind: 'accepted' }
      >['targetReference'],
      expectedVersion: 1,
      d5: body.change.d5,
      confirmedContent: body.change.payload,
      acceptedAt: raw.accepted_at,
    }
  }
  if (
    !['B8', 'B9', 'B10', 'B11', 'B12', 'B13', 'B14'].includes(
      String(raw.boundary),
    ) ||
    !exact(raw, ['boundary', 'd5', 'reason']) ||
    (raw.reason !== null && typeof raw.reason !== 'string')
  )
    throw new Error('P3拒否結果の封筒が不正です')
  return {
    kind: 'rejected',
    boundary: raw.boundary as Extract<
      P3ProductResult,
      { kind: 'rejected' }
    >['boundary'],
    d5: body.change.d5,
  }
}

/** HTTP 200でも受理全組が一致しなければ成功としない。 */
export async function postP3Change(
  body: P3ChangeBody,
  credentials: SyncRequestCredentials,
): Promise<P3ProductResult> {
  const sent = await postRecoverableP3Change(
    body.change.game_id,
    body,
    credentials,
  )
  return parseResult(sent.response, sent.body)
}

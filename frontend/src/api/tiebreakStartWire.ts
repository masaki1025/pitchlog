/** タイブレーク開始P2の閉じたV7。保存資格とACKは既同期境界へ委ねる。 */
import type { CheckpointRef } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import {
  buildSyncEventRequestBody,
  SYNC_EVENT_SEND_FAILURE,
  type SyncEventRequestBody,
  type SyncEventSendRequest,
  type SyncEventSendResult,
} from './client.syncEvents'
import { ApiError } from './client'
import { postRecoverableSyncRequest } from './recoverableSyncPost'
import { canonicalUuid } from './authIntent'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'

export const TIEBREAK_START_FORMAT = 'tiebreak-start-event-v1' as const
export const TIEBREAK_START_KIND = EVENT_KIND_RULES.find(
  (kind) => kind.id === '4' && kind.name === 'タイブレーク開始',
)!

export type TiebreakStartPayload = Readonly<{
  formatVersion: typeof TIEBREAK_START_FORMAT
  expectedCheckpoint: CheckpointRef
  eventId: string
  runnerPlacement: 'first-second' | 'second-third'
  leadoffBatter: string
  inning: string
  firstRunnerId: string
  secondRunnerId: string
}>

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
const exact = (
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> =>
  record(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key))
const uuid = (value: unknown): value is string =>
  typeof value === 'string' && canonicalUuid.test(value)
const decimal = (value: unknown): value is string =>
  typeof value === 'string' && /^[1-9][0-9]*$/.test(value)
const oneToNine = (value: unknown): value is string =>
  typeof value === 'string' && /^[1-9]$/.test(value)

export function isTiebreakStartPayload(
  value: unknown,
): value is TiebreakStartPayload {
  if (
    !exact(value, [
      'formatVersion',
      'expectedCheckpoint',
      'eventId',
      'runnerPlacement',
      'leadoffBatter',
      'inning',
      'firstRunnerId',
      'secondRunnerId',
    ]) ||
    value.formatVersion !== TIEBREAK_START_FORMAT ||
    !exact(value.expectedCheckpoint, ['id', 'revision', 'digest']) ||
    !uuid(value.expectedCheckpoint.id) ||
    !decimal(value.expectedCheckpoint.revision) ||
    typeof value.expectedCheckpoint.digest !== 'string' ||
    !/^[0-9a-f]{64}$/.test(value.expectedCheckpoint.digest) ||
    !uuid(value.eventId) ||
    (value.runnerPlacement !== 'first-second' &&
      value.runnerPlacement !== 'second-third') ||
    !oneToNine(value.leadoffBatter) ||
    !decimal(value.inning) ||
    !uuid(value.firstRunnerId) ||
    !uuid(value.secondRunnerId) ||
    value.firstRunnerId === value.secondRunnerId
  )
    return false
  return true
}

export function tiebreakStartEvent(
  gameId: string,
  d4: string,
  d5: string,
  d2: number,
  payload: TiebreakStartPayload,
): SyncEvent {
  if (
    !uuid(gameId) ||
    !uuid(d5) ||
    !d4 ||
    !Number.isSafeInteger(d2) ||
    d2 < 0 ||
    !isTiebreakStartPayload(payload)
  )
    throw new Error('タイブレーク開始イベントが閉境界に適合しません')
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: TIEBREAK_START_KIND.id,
      V6: d2,
      V7: payload,
    },
  }
}

export function tiebreakStartBody(
  request: SyncEventSendRequest,
): SyncEventRequestBody {
  const body = buildSyncEventRequestBody({
    gameId: request.gameId,
    recordingRightProof: request.recordingRightProof,
    slots: request.slots,
    eventKinds: request.eventKinds,
  })
  if (!('events' in body) || body.events.length !== 1)
    throw new Error('タイブレーク開始本文が単一イベントではありません')
  const event = body.events[0]
  if (
    event?.event_kind !== TIEBREAK_START_KIND.id ||
    !isTiebreakStartPayload(event.payload)
  )
    throw new Error('タイブレーク開始本文が閉境界に適合しません')
  // 画面の参加区分IDと、DB/P1が要求する保存種別literalをこの専用wireで対応付ける。
  return {
    recording_right_proof: body.recording_right_proof,
    events: [{ ...event, event_kind: 'tiebreak_start' }],
  }
}

export async function postTiebreakStart(
  request: SyncEventSendRequest,
): Promise<SyncEventSendResult> {
  const credentials = request.syncCredentials
  if (credentials === undefined)
    return { sent: false, reason: SYNC_EVENT_SEND_FAILURE.NO_RESPONSE }
  const requestBody = tiebreakStartBody(request)
  try {
    const sent = await postRecoverableSyncRequest(
      request.gameId,
      requestBody,
      credentials,
    )
    return { sent: true, requestBody: sent.body, response: sent.response }
  } catch (error) {
    if (error instanceof ApiError)
      return {
        sent: false,
        reason: SYNC_EVENT_SEND_FAILURE.RESPONSE_NOT_INTERPRETED,
        status: error.status,
        error,
      }
    return { sent: false, reason: SYNC_EVENT_SEND_FAILURE.NO_RESPONSE, error }
  }
}

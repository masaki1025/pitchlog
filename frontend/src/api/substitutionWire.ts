/** 交代P2の閉じたV7。採番・ACK・保存資格は既同期境界に委ねる。 */
import type { CheckpointRef } from '../../../contracts/state-transition/nonplay_prefix_bridge_v1'
import {
  buildSyncEventRequestBody,
  SYNC_EVENT_SEND_FAILURE,
  type SyncEventRequestBody,
  type SyncEventSendResult,
} from './client.syncEvents'
import { ApiError, apiRequest, type SyncRequestCredentials } from './client'
import { canonicalUuid } from './authIntent'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'
import {
  isSubstitutionOperation,
  type SubstitutionOperation,
} from '../domain/substitutionKernel'

export const SUBSTITUTION_FORMAT = 'substitution-event-v1' as const
export const SUBSTITUTION_KIND = EVENT_KIND_RULES.find(
  (kind) => kind.id === '3' && kind.name === '選手交代',
)!
export type SubstitutionPayload = Readonly<{
  formatVersion: typeof SUBSTITUTION_FORMAT
  expectedCheckpoint: CheckpointRef
  eventId: string
  operation: SubstitutionOperation
  incomingSnapshots: readonly Readonly<{
    playerId: string
    uniformNumber: string | null
  }>[]
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

export function isSubstitutionPayload(
  value: unknown,
): value is SubstitutionPayload {
  if (
    !exact(value, [
      'formatVersion',
      'expectedCheckpoint',
      'eventId',
      'operation',
      'incomingSnapshots',
    ]) ||
    value.formatVersion !== SUBSTITUTION_FORMAT ||
    !exact(value.expectedCheckpoint, ['id', 'revision', 'digest']) ||
    !uuid(value.expectedCheckpoint.id) ||
    !decimal(value.expectedCheckpoint.revision) ||
    typeof value.expectedCheckpoint.digest !== 'string' ||
    !/^[0-9a-f]{64}$/.test(value.expectedCheckpoint.digest) ||
    !uuid(value.eventId) ||
    !isSubstitutionOperation(value.operation) ||
    !Array.isArray(value.incomingSnapshots)
  )
    return false
  const incoming =
    value.operation.kind === 'defense'
      ? value.operation.changes
          .map((change) => change.incomingId)
          .filter((id): id is string => id !== null)
      : [value.operation.incomingId]
  if (
    new Set(incoming).size !== incoming.length ||
    value.incomingSnapshots.length !== incoming.length ||
    value.incomingSnapshots.some(
      (entry, index) =>
        !exact(entry, ['playerId', 'uniformNumber']) ||
        entry.playerId !== incoming[index] ||
        (entry.uniformNumber !== null &&
          typeof entry.uniformNumber !== 'string'),
    )
  )
    return false
  return true
}

export function substitutionEvent(
  gameId: string,
  d4: string,
  d5: string,
  d2: number,
  payload: SubstitutionPayload,
): SyncEvent {
  if (
    !uuid(gameId) ||
    !uuid(d5) ||
    !d4 ||
    !Number.isSafeInteger(d2) ||
    d2 < 0 ||
    !isSubstitutionPayload(payload)
  )
    throw new Error('交代イベントが閉境界に適合しません')
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: SUBSTITUTION_KIND.id,
      V6: d2,
      V7: payload,
    },
  }
}

export function substitutionBody(
  slotValue: DurableQueueSlot,
  recordingRightProof: unknown,
): SyncEventRequestBody {
  const body = buildSyncEventRequestBody({
    gameId: String(slotValue.game),
    recordingRightProof,
    slots: [slotValue],
    eventKinds: [SUBSTITUTION_KIND],
  })
  if (
    !('events' in body) ||
    body.events.length !== 1 ||
    body.events[0]?.event_kind !== SUBSTITUTION_KIND.id ||
    !isSubstitutionPayload(body.events[0]?.payload)
  )
    throw new Error('保存交代本文が閉境界に適合しません')
  // 画面の参加区分IDと、DB/P1が要求する保存種別literalをこの専用wireで対応付ける。
  return {
    recording_right_proof: body.recording_right_proof,
    events: [{ ...body.events[0], event_kind: 'substitution' }],
  }
}

export async function postSubstitution(
  slotValue: DurableQueueSlot,
  recordingRightProof: unknown,
  credentials: SyncRequestCredentials,
): Promise<SyncEventSendResult> {
  const requestBody = substitutionBody(slotValue, recordingRightProof)
  try {
    const response = await apiRequest<unknown>(
      'POST',
      `/games/${encodeURIComponent(String(slotValue.game))}/sync/events`,
      { tenantBound: true, body: requestBody, syncCredentials: credentials },
    )
    return { sent: true, requestBody, response }
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

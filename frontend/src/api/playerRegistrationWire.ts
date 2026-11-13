/**
 * その場登録（FR-015）の E-1 wire と A4 写像の受け取り。
 *
 * 端末キューには登録側原入力（V7）を保存し、送信時だけ wire 3-2 の
 * `registration` と `payload: { player_id }` へ分ける。サーバーの選手行・
 * 一時 ID 写像の作成は適用核が所有し、ここでは本文の組み立てと応答の解釈だけを
 * 行う（docs/design/sync-protocol.md 4-4・7-1）。
 */
import { canonicalUuid } from './authIntent'
import { ApiError, type SyncRequestCredentials } from './client'
import {
  buildSyncEventRequestBody,
  SYNC_EVENT_SEND_FAILURE,
  type SyncEventRequestBody,
  type SyncEventSendResult,
} from './client.syncEvents'
import { parseD1AckEnvelope } from '../lib/sync/ackEnvelope'
import {
  CANON_ACK_STATE_RESULT,
  readCanonBoundaryResults,
} from '../lib/sync/canonOracle'
import { EVENT_KIND_RULES } from '../lib/sync/eventKinds'
import { SYNC_EVENT_PATH } from '../lib/sync/eventFieldRules'
import type { DurableQueueSlot } from '../lib/sync/durableQueue'
import type { SyncEvent } from '../lib/sync/syncEvent'
import { checkSyncEvent } from '../lib/sync/validateSyncEvent'
import type { AckResponse } from '../screens/GameScreenAckApplication'
import { postRecoverableSyncRequest } from './recoverableSyncPost'

export const PLAYER_REGISTRATION_INPUT_FORMAT =
  'player-registration-input-v1' as const
export const PLAYER_REGISTRATION_KIND = (() => {
  const kind = EVENT_KIND_RULES.find(
    (candidate) => candidate.name === '選手のその場登録',
  )
  if (!kind) throw new Error('選手登録イベント種別がありません')
  return kind
})()

export type PlayerRegistrationInput = Readonly<{
  formatVersion: typeof PLAYER_REGISTRATION_INPUT_FORMAT
  temporaryId: string
  teamRecordId: string
  name: string
  throws: 'right' | 'left' | null
  bats: 'right' | 'left' | 'both' | null
  uniformNumber: string | null
  rosterStatusKey: string
}>

const INPUT_KEYS = [
  'formatVersion',
  'temporaryId',
  'teamRecordId',
  'name',
  'throws',
  'bats',
  'uniformNumber',
  'rosterStatusKey',
] as const
const BODY_EVENT_KEYS = [
  'd5',
  'd1',
  'd4',
  'game_id',
  'event_kind',
  'payload',
  'registration',
] as const
const REGISTRATION_WIRE_KEYS = [
  'temporary_id',
  'team_record_id',
  'name',
  'roster_status_key',
] as const
const REGISTRATION_OPTIONAL_WIRE_KEYS = [
  'throws',
  'bats',
  'uniform_number',
] as const

const record = (value: unknown): value is Record<string, unknown> =>
  value !== null &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  (Object.getPrototypeOf(value) === Object.prototype ||
    Object.getPrototypeOf(value) === null)

const exact = (
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> =>
  record(value) &&
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key))

const uuid = (value: unknown): value is string =>
  typeof value === 'string' && canonicalUuid.test(value)

const text = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0

export function isPlayerRegistrationInput(
  value: unknown,
): value is PlayerRegistrationInput {
  if (!exact(value, INPUT_KEYS)) return false
  return (
    value.formatVersion === PLAYER_REGISTRATION_INPUT_FORMAT &&
    uuid(value.temporaryId) &&
    uuid(value.teamRecordId) &&
    text(value.name) &&
    value.name.trim() === value.name &&
    (value.throws === null ||
      value.throws === 'right' ||
      value.throws === 'left') &&
    (value.bats === null ||
      value.bats === 'right' ||
      value.bats === 'left' ||
      value.bats === 'both') &&
    (value.uniformNumber === null || text(value.uniformNumber)) &&
    text(value.rosterStatusKey)
  )
}

/** キューへ入れる登録側原入力。一時 ID は採番時に固定し、再送で作り直さない。 */
export function playerRegistrationInput(
  value: Omit<PlayerRegistrationInput, 'formatVersion'>,
): PlayerRegistrationInput {
  const input: PlayerRegistrationInput = {
    formatVersion: PLAYER_REGISTRATION_INPUT_FORMAT,
    ...value,
  }
  if (!isPlayerRegistrationInput(input))
    throw new Error('その場登録の入力が閉境界に適合しません')
  return Object.freeze(input)
}

/** D1 を持たない登録イベント。D1 はキュー追記時に採番される。 */
export function playerRegistrationEvent(
  gameId: string,
  d4: string,
  d5: string,
  input: PlayerRegistrationInput,
): SyncEvent {
  if (
    !uuid(gameId) ||
    !uuid(d5) ||
    !text(d4) ||
    !isPlayerRegistrationInput(input)
  )
    throw new Error('その場登録イベントが閉境界に適合しません')
  return {
    fields: {
      V1: d5,
      V3: d4,
      V4: gameId,
      V5: PLAYER_REGISTRATION_KIND.id,
      V7: structuredClone(input),
    },
  }
}

function registrationWire(input: PlayerRegistrationInput) {
  const wire: Record<string, unknown> = {
    temporary_id: input.temporaryId,
    team_record_id: input.teamRecordId,
    name: input.name,
    roster_status_key: input.rosterStatusKey,
  }
  if (input.throws !== null) wire.throws = input.throws
  if (input.bats !== null) wire.bats = input.bats
  if (input.uniformNumber !== null) wire.uniform_number = input.uniformNumber
  if (
    !REGISTRATION_WIRE_KEYS.every((key) => Object.hasOwn(wire, key)) ||
    Object.keys(wire).some(
      (key) =>
        !REGISTRATION_WIRE_KEYS.includes(
          key as (typeof REGISTRATION_WIRE_KEYS)[number],
        ) &&
        !REGISTRATION_OPTIONAL_WIRE_KEYS.includes(
          key as (typeof REGISTRATION_OPTIONAL_WIRE_KEYS)[number],
        ),
    )
  )
    throw new Error('その場登録の registration が閉じていません')
  return wire
}

/**
 * 保存済みスロットから送信本文を組み立てる。
 *
 * `payload` は核が要求する一時 ID 1 件、`registration` は選手作成値である。
 * 同じスロットからは常に同じ本文を作り、再送で内容を作り直さない。
 */
export function playerRegistrationBody(
  slot: DurableQueueSlot,
  recordingRightProof: unknown,
): SyncEventRequestBody {
  const fields = { ...slot.event.fields, V2: slot.d1 }
  if (
    slot.event.fields.V5 !== PLAYER_REGISTRATION_KIND.id ||
    slot.event.fields.V1 !== slot.d5 ||
    slot.event.fields.V3 !== slot.d4 ||
    slot.event.fields.V4 !== slot.game ||
    !isPlayerRegistrationInput(slot.event.fields.V7)
  )
    throw new Error('保存済みその場登録の形式が不一致です')
  if (
    !checkSyncEvent(
      { fields },
      { path: SYNC_EVENT_PATH.P1, eventKinds: [PLAYER_REGISTRATION_KIND] },
    ).ok
  )
    throw new Error('その場登録のイベント契約が不一致です')
  const input = slot.event.fields.V7
  const body = buildSyncEventRequestBody({
    gameId: String(slot.game),
    recordingRightProof,
    slots: [slot],
    eventKinds: [PLAYER_REGISTRATION_KIND],
  })
  if (
    'sent' in body ||
    body.events.length !== 1 ||
    body.events[0]?.d2 !== undefined
  )
    throw new Error('その場登録の保存本文を形成できません')
  const event: Record<string, unknown> = {
    ...body.events[0],
    event_kind: 'player_registration',
    payload: { player_id: input.temporaryId },
    registration: registrationWire(input),
  }
  if (
    !exact(event, BODY_EVENT_KEYS) ||
    event.d5 !== slot.d5 ||
    event.d1 !== slot.d1 ||
    event.d4 !== slot.d4 ||
    event.game_id !== slot.game ||
    event.event_kind !== 'player_registration'
  )
    throw new Error('その場登録の wire が閉境界に適合しません')
  return { recording_right_proof: body.recording_right_proof, events: [event] }
}

export async function postPlayerRegistration(
  slot: DurableQueueSlot,
  recordingRightProof: unknown,
  credentials: SyncRequestCredentials,
): Promise<SyncEventSendResult> {
  const requestBody = playerRegistrationBody(slot, recordingRightProof)
  try {
    const sent = await postRecoverableSyncRequest(
      String(slot.game),
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

export type PlayerRegistrationAck = Readonly<{
  ack: AckResponse
  mapping: Readonly<{ temporaryId: string; officialId: string }>
}>

/**
 * 登録イベント 1 件の ACK から A4 写像を取り出す。
 *
 * A5 が受理・重複でも、写像が欠ける・余分・別イベント宛なら解釈しない
 * （4-4 の C4）。写像が返らない ACK でスロットを同期済みにしない。
 */
export function readPlayerRegistrationAck(
  value: unknown,
  key: Readonly<{
    d4: string
    d1: number
    d5: string
    temporaryId: string
  }>,
): PlayerRegistrationAck | undefined {
  try {
    if (
      !text(key.d4) ||
      !Number.isSafeInteger(key.d1) ||
      key.d1 < 1 ||
      !uuid(key.d5) ||
      !uuid(key.temporaryId)
    )
      return undefined
    const envelope = parseD1AckEnvelope(value)
    if (envelope.eventResults.length !== 1) return undefined
    const item = envelope.eventResults[0]!
    if (
      item.d4 !== key.d4 ||
      item.d1 !== key.d1 ||
      item.d5 !== key.d5 ||
      (item.a5Result.id !== CANON_ACK_STATE_RESULT.ACCEPTED &&
        item.a5Result.id !== CANON_ACK_STATE_RESULT.DUPLICATE)
    )
      return undefined
    if (!envelope.playerIdMappings || envelope.playerIdMappings.length !== 1)
      return undefined
    const mapping = envelope.playerIdMappings[0]!
    if (
      mapping.temporaryId !== key.temporaryId ||
      !uuid(mapping.officialId) ||
      mapping.officialId === key.temporaryId
    )
      return undefined
    const terminal = readCanonBoundaryResults().find(
      (row) => row.name === '要求終端',
    )
    if (!terminal) return undefined
    return {
      ack: { envelope: value, boundaryResult: terminal.id },
      mapping: {
        temporaryId: mapping.temporaryId as string,
        officialId: mapping.officialId as string,
      },
    }
  } catch {
    return undefined
  }
}

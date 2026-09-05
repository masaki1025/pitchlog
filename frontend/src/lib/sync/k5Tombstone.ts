// この規則と生成条件は docs/design/sync-protocol.md 5-5・6-4・7-2 の K5 の写しである。
// 記録権の成立判定は requestBoundary の verifier に委ね、値の形式は解釈しない。

import { SYNC_EVENT_PATH } from './eventFieldRules'
import type { DurableQueueSlot } from './durableQueue'
import {
  checkRequestBoundary,
  type RequestBoundaryEnvelope,
  type V12BindingVerifier,
} from './requestBoundary'
import { actionRequiredLabelId, queueStateId } from './queueState'

const UNSENT_STATE = queueStateId('未送信')
const ACTION_REQUIRED_STATE = queueStateId('要操作')
const REVISION_ACTION_LABEL_ID = actionRequiredLabelId('改訂待ち')
const TOMBSTONE_ACTION_LABEL_ID = actionRequiredLabelId('墓標待ち')

type K5TombstoneRuleDefinition = Readonly<{
  id: string
  name: string
  conditions: readonly Readonly<{ id: string }>[]
}>

export const K5_TOMBSTONE_RULE = {
  id: 'K5',
  name: '墓標生成',
  conditions: [{ id: 'オンライン記録権確認後' }, { id: 'D1付きキュー' }],
} as const satisfies K5TombstoneRuleDefinition

type ActionGenerationRuleDefinition = Readonly<{
  actionRequiredLabel: string
  localGenerationAllowed: boolean
  onlineRecordingRightRequired: boolean
}>

export const K5_ACTION_GENERATION_RULES = [
  {
    actionRequiredLabel: REVISION_ACTION_LABEL_ID,
    localGenerationAllowed: true,
    onlineRecordingRightRequired: false,
  },
  {
    actionRequiredLabel: TOMBSTONE_ACTION_LABEL_ID,
    localGenerationAllowed: false,
    onlineRecordingRightRequired: true,
  },
] as const satisfies readonly ActionGenerationRuleDefinition[]

export const TOMBSTONE_ONLINE_STATE = {
  ONLINE: 'オンライン',
  OFFLINE: 'オフライン',
  UNKNOWN: '不明',
} as const

export type TombstoneOnlineState =
  (typeof TOMBSTONE_ONLINE_STATE)[keyof typeof TOMBSTONE_ONLINE_STATE]

export type TombstoneSourceSlot = DurableQueueSlot

type D1RequestBoundaryEnvelope = Exclude<
  RequestBoundaryEnvelope,
  { path: typeof SYNC_EVENT_PATH.P3 }
>

export type TombstoneBoundaryRequest = D1RequestBoundaryEnvelope &
  Readonly<{
    game: unknown
    d4: unknown
    d1: number
  }>

export type TombstoneRecordingRightVerifier = (
  input: Parameters<V12BindingVerifier>[0],
) => ReturnType<V12BindingVerifier> | undefined

export type TombstoneGenerationRequest = Readonly<{
  slot: TombstoneSourceSlot
  tombstoneVersion: unknown
  boundaryRequest: TombstoneBoundaryRequest
}>

export type TombstoneGenerationInjections = Readonly<{
  resolveOnlineState?: () => TombstoneOnlineState | undefined
  v12Binding?: TombstoneRecordingRightVerifier
  generateD5?: () => unknown
  allocateD1?: () => unknown
}>

type EmptyTombstoneContent = Readonly<Record<string, never>>
type EmptyTombstoneEvent = Readonly<{
  fields: EmptyTombstoneContent
}>

export type TombstoneQueueSlotReplacement = Readonly<{
  game: TombstoneSourceSlot['game']
  d4: TombstoneSourceSlot['d4']
  d1: TombstoneSourceSlot['d1']
  d5: TombstoneSourceSlot['d5']
  version: TombstoneSourceSlot['version']
  event: EmptyTombstoneEvent
  state: typeof UNSENT_STATE
}>

export type TombstoneGenerationResult =
  | Readonly<{
      offered: false
      slot: TombstoneSourceSlot
    }>
  | Readonly<{
      offered: true
      replacement: TombstoneQueueSlotReplacement
    }>

function notOffered(slot: TombstoneSourceSlot): TombstoneGenerationResult {
  return Object.freeze({ offered: false, slot })
}

function hasSameEventIdentity(
  slot: TombstoneSourceSlot,
  boundaryRequest: TombstoneBoundaryRequest,
): boolean {
  return (
    Object.is(slot.game, boundaryRequest.game) &&
    Object.is(slot.d4, boundaryRequest.d4) &&
    Object.is(slot.d1, boundaryRequest.d1)
  )
}

export function prepareTombstoneReplacement(
  request: TombstoneGenerationRequest,
  injections: TombstoneGenerationInjections = {},
): TombstoneGenerationResult {
  const { slot } = request
  if (
    slot.state !== ACTION_REQUIRED_STATE ||
    slot.actionRequiredLabel !== TOMBSTONE_ACTION_LABEL_ID ||
    !hasSameEventIdentity(slot, request.boundaryRequest)
  ) {
    return notOffered(slot)
  }

  let onlineState: TombstoneOnlineState | undefined
  try {
    onlineState = injections.resolveOnlineState?.()
  } catch {
    return notOffered(slot)
  }
  if (onlineState !== TOMBSTONE_ONLINE_STATE.ONLINE) {
    return notOffered(slot)
  }

  const verifier = injections.v12Binding
  if (!verifier) {
    return notOffered(slot)
  }
  const boundaryResult = checkRequestBoundary(request.boundaryRequest, {
    v12Binding: (input) => verifier(input) === true,
  })
  if (!boundaryResult.ok) {
    return notOffered(slot)
  }

  const generateD5 = injections.generateD5
  if (!generateD5) {
    return notOffered(slot)
  }

  let newD5: unknown
  try {
    newD5 = generateD5()
  } catch {
    return notOffered(slot)
  }
  if (newD5 === undefined || Object.is(newD5, slot.d5)) {
    return notOffered(slot)
  }

  // allocateD1 は不使用のまま注入可能にし、新しい D1 を採番しない契約を観測可能にする。
  const content: EmptyTombstoneContent = Object.freeze({})
  const event: EmptyTombstoneEvent = Object.freeze({ fields: content })
  const replacement: TombstoneQueueSlotReplacement = Object.freeze({
    game: slot.game,
    d4: slot.d4,
    d1: slot.d1,
    d5: newD5,
    version: request.tombstoneVersion,
    event,
    state: UNSENT_STATE,
  })

  return Object.freeze({ offered: true, replacement })
}

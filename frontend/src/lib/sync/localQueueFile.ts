// このファイル境界は docs/design/sync-protocol.md 7-7 の X1〜X4 と、
// docs/features/sync-queue-lifecycle/plan.md 4 節のファイル形式の実装である。
// 識別値の形式は解釈せず、codec の往復同値性だけを検査する。

import {
  readCanonV12BoundaryRules,
  type CanonV12BoundaryRule,
} from './canonOracle'
import type { DurableQueueSlot } from './durableQueue'
import {
  checkRequestBoundary,
  REQUEST_BOUNDARY_RESULT,
  type RequestBoundaryEnvelope,
  type V12BindingVerifier,
} from './requestBoundary'
import { queueStateId, type QueueStateId } from './queueState'

const EVACUATED_STATE = queueStateId('退避済み')

const LOCAL_QUEUE_V12_BOUNDARY_RULE_IDS = ['VF1', 'VF4'] as const

function readLocalQueueV12BoundaryRules(): readonly CanonV12BoundaryRule[] {
  const canonRules = readCanonV12BoundaryRules()
  return LOCAL_QUEUE_V12_BOUNDARY_RULE_IDS.map((id) => {
    const rule = canonRules.find((candidate) => candidate.id === id)
    if (!rule) {
      throw new Error(`ローカルファイル境界の規則がありません: ${id}`)
    }
    return rule
  })
}

export const LOCAL_QUEUE_V12_BOUNDARY_RULES = Object.freeze(
  readLocalQueueV12BoundaryRules(),
)

const LOCAL_QUEUE_PRESENCE_RULE = LOCAL_QUEUE_V12_BOUNDARY_RULES.find(
  (rule) => rule.effect.kind === 'presence',
)
const LOCAL_QUEUE_FAILURE_RULE = LOCAL_QUEUE_V12_BOUNDARY_RULES.find(
  (rule) => rule.effect.kind === 'failure',
)
if (
  LOCAL_QUEUE_V12_BOUNDARY_RULES.length !== 2 ||
  LOCAL_QUEUE_PRESENCE_RULE?.effect.kind !== 'presence' ||
  LOCAL_QUEUE_PRESENCE_RULE.effect.required !== true ||
  LOCAL_QUEUE_FAILURE_RULE?.effect.kind !== 'failure' ||
  LOCAL_QUEUE_FAILURE_RULE.effect.result !== REQUEST_BOUNDARY_RESULT.B4
) {
  throw new Error('ローカルファイル境界の規則が不正です')
}

export type LocalQueueFileEnvelope = Readonly<{
  schemaVersion: unknown
  exportedAt: unknown
  events: readonly DurableQueueSlot[]
}>

export type LocalQueueFileCodec = Readonly<{
  encode: (value: LocalQueueFileEnvelope) => string
  decode: (text: string) => unknown
}>

export class LocalQueueFileError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'LocalQueueFileError'
  }
}

export const DEFAULT_LOCAL_QUEUE_FILE_CODEC: LocalQueueFileCodec =
  Object.freeze({
    encode: (value) => {
      const text = JSON.stringify(value)
      if (text === undefined) {
        throw new LocalQueueFileError('JSON テキストを生成できません')
      }
      return text
    },
    decode: (text) => JSON.parse(text) as unknown,
  })

export type LocalQueueFileExportRequest = Readonly<{
  schemaVersion: unknown
  exportedAt: unknown
  events: readonly DurableQueueSlot[]
}>

export type LocalQueueFileExportInjections = Readonly<{
  codec?: LocalQueueFileCodec
  writeOutput?: (text: string) => void | Promise<void>
  allocateD1?: () => unknown
}>

function structurallyEquivalent(
  first: unknown,
  second: unknown,
  visited = new WeakMap<object, object>(),
): boolean {
  if (Object.is(first, second)) {
    return true
  }
  if (
    typeof first !== 'object' ||
    first === null ||
    typeof second !== 'object' ||
    second === null ||
    Object.getPrototypeOf(first) !== Object.getPrototypeOf(second)
  ) {
    return false
  }

  const previousSecond = visited.get(first)
  if (previousSecond !== undefined) {
    return previousSecond === second
  }
  visited.set(first, second)

  const firstKeys = Reflect.ownKeys(first)
  const secondKeys = Reflect.ownKeys(second)
  if (
    firstKeys.length !== secondKeys.length ||
    firstKeys.some((key) => !Object.hasOwn(second, key))
  ) {
    return false
  }
  return firstKeys.every((key) =>
    structurallyEquivalent(
      Reflect.get(first, key),
      Reflect.get(second, key),
      visited,
    ),
  )
}

export async function exportLocalQueueFile(
  request: LocalQueueFileExportRequest,
  injections: LocalQueueFileExportInjections = {},
): Promise<string> {
  const envelope: LocalQueueFileEnvelope = {
    schemaVersion: request.schemaVersion,
    exportedAt: request.exportedAt,
    events: request.events,
  }
  const codec = injections.codec ?? DEFAULT_LOCAL_QUEUE_FILE_CODEC

  let text: string
  let decoded: unknown
  try {
    text = codec.encode(envelope)
    JSON.parse(text)
    decoded = codec.decode(text)
  } catch (error) {
    throw new LocalQueueFileError('ローカルキューファイルを生成できません', {
      cause: error,
    })
  }
  if (!structurallyEquivalent(envelope, decoded)) {
    throw new LocalQueueFileError('codec の往復でイベントの原形が変わります')
  }

  await injections.writeOutput?.(text)
  return text
}

type LocalQueueBoundaryRequest = Extract<
  RequestBoundaryEnvelope,
  { p3State?: never }
>

export type LocalQueueFileProvenance = Readonly<{
  sameDevice: boolean
  sameBrowser: boolean
}>

export type LocalQueueFileImportInjections = Readonly<{
  codec?: LocalQueueFileCodec
  resolveProvenance?: (
    envelope: LocalQueueFileEnvelope,
  ) => LocalQueueFileProvenance | undefined
  v12Binding?: V12BindingVerifier
}>

export const LOCAL_QUEUE_IMPORT_STATUS = {
  COMPLETED: 'completed',
  OUTSIDE_GUARANTEE: 'outside-guarantee',
} as const

export type LocalQueueB4Event = Readonly<{
  result: typeof REQUEST_BOUNDARY_RESULT.B4
  event: DurableQueueSlot
}>

export type LocalQueueFileImportRequest = Readonly<{
  text: string
  currentD4: unknown
  boundaryRequest: LocalQueueBoundaryRequest
  existingEvents: readonly DurableQueueSlot[]
}>

export type LocalQueueFileImportResult = Readonly<{
  status: (typeof LOCAL_QUEUE_IMPORT_STATUS)[keyof typeof LOCAL_QUEUE_IMPORT_STATUS]
  importedEvents: readonly DurableQueueSlot[]
  duplicateEvents: readonly DurableQueueSlot[]
  b4Events: readonly LocalQueueB4Event[]
  notImportedEvents: readonly DurableQueueSlot[]
}>

const ENVELOPE_KEYS = ['schemaVersion', 'exportedAt', 'events'] as const
const EVENT_KEYS = [
  'game',
  'd4',
  'd1',
  'd5',
  'version',
  'event',
  'state',
] as const

function isRecord(value: unknown): value is Record<PropertyKey, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasRequiredKeys(
  value: Record<PropertyKey, unknown>,
  keys: readonly string[],
): boolean {
  return keys.every((key) => Object.hasOwn(value, key))
}

function isDurableQueueSlot(value: unknown): value is DurableQueueSlot {
  if (!isRecord(value) || !hasRequiredKeys(value, EVENT_KEYS)) {
    return false
  }
  try {
    queueStateId(value.state as QueueStateId)
  } catch {
    return false
  }
  return true
}

function decodeEnvelope(
  text: string,
  codec: LocalQueueFileCodec,
): LocalQueueFileEnvelope {
  let decoded: unknown
  try {
    JSON.parse(text)
    decoded = codec.decode(text)
  } catch (error) {
    throw new LocalQueueFileError('ローカルキューファイルを読めません', {
      cause: error,
    })
  }

  if (
    !isRecord(decoded) ||
    Reflect.ownKeys(decoded).length !== ENVELOPE_KEYS.length ||
    !hasRequiredKeys(decoded, ENVELOPE_KEYS) ||
    !Array.isArray(decoded.events) ||
    !decoded.events.every(isDurableQueueSlot)
  ) {
    throw new LocalQueueFileError('ローカルキューファイルの構造が不正です')
  }
  return decoded as LocalQueueFileEnvelope
}

function outsideGuarantee(): LocalQueueFileImportResult {
  return {
    status: LOCAL_QUEUE_IMPORT_STATUS.OUTSIDE_GUARANTEE,
    importedEvents: [],
    duplicateEvents: [],
    b4Events: [],
    notImportedEvents: [],
  }
}

function hasSameD5(
  events: readonly DurableQueueSlot[],
  candidate: DurableQueueSlot,
): boolean {
  return events.some((event) => Object.is(event.d5, candidate.d5))
}

export function importLocalQueueFile(
  request: LocalQueueFileImportRequest,
  injections: LocalQueueFileImportInjections = {},
): LocalQueueFileImportResult {
  const codec = injections.codec ?? DEFAULT_LOCAL_QUEUE_FILE_CODEC
  const envelope = decodeEnvelope(request.text, codec)

  let provenance: LocalQueueFileProvenance | undefined
  try {
    provenance = injections.resolveProvenance?.(envelope)
  } catch {
    return outsideGuarantee()
  }
  if (provenance?.sameDevice !== true || provenance.sameBrowser !== true) {
    return outsideGuarantee()
  }

  const boundaryResult = checkRequestBoundary(request.boundaryRequest, {
    v12Binding: injections.v12Binding,
  })
  const boundaryAccepted = boundaryResult.ok
  const importedEvents: DurableQueueSlot[] = []
  const duplicateEvents: DurableQueueSlot[] = []
  const b4Events: LocalQueueB4Event[] = []
  const notImportedEvents: DurableQueueSlot[] = []

  for (const event of envelope.events) {
    if (event.state === EVACUATED_STATE) {
      notImportedEvents.push(event)
      continue
    }
    if (!Object.is(event.d4, request.currentD4) || !boundaryAccepted) {
      b4Events.push({
        result: REQUEST_BOUNDARY_RESULT.B4,
        event: { ...event, state: EVACUATED_STATE },
      })
      continue
    }
    if (
      hasSameD5(request.existingEvents, event) ||
      hasSameD5(importedEvents, event)
    ) {
      duplicateEvents.push(event)
      continue
    }
    importedEvents.push(event)
  }

  return {
    status: LOCAL_QUEUE_IMPORT_STATUS.COMPLETED,
    importedEvents,
    duplicateEvents,
    b4Events,
    notImportedEvents,
  }
}

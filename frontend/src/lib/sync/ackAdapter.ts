// このアダプタは D1 ACK と P3 独立応答を、既存のクライアント注入境界へ接続する。
// 応答が無い経路や、この 2 経路を供給元としない境界は未注入のままにする。

import {
  parseD1AckEnvelope,
  type D1AckEnvelope,
  type D1AckEventResult,
} from './ackEnvelope'
import { parseAckBoundaryResult } from './boundaryResults'
import type {
  I6PersistenceInjections,
  I6AcceptedAtResolution,
} from './durableQueue'
import type { KeyBoundMappingResolver } from './durableQueue'
import { parseP3ResultEnvelope } from './p3Result'
import {
  receivePlayerIdMapping,
  type PlayerIdMappingTarget,
} from './playerIdMapping'
import { parseB3Rejection, type B3Rejection } from './rejectionReason'
import type {
  QueueEventKey,
  QueueTransitionInjections,
} from './queueTransition'
import type { I6Acceptance } from './queueState'

const B3_BOUNDARY_RESULT_ID = 'B3'

type D1QueueTransitionInjections = Pick<
  QueueTransitionInjections,
  'resolveA5' | 'classifyB3'
>

export type D1AckAdapterInput = Readonly<{
  envelope: unknown
  boundaryResult: unknown
  b3Rejection?: unknown
  playerIdMappingTarget?: PlayerIdMappingTarget
}>

export type P3ResultAdapterInput = Readonly<{
  envelope: unknown
  expected: I6Acceptance
}>

export type AckAdapterRequest = Readonly<{
  d1?: D1AckAdapterInput
  p3?: P3ResultAdapterInput
}>

type KeyBoundMappingInjections = Readonly<{
  resolvePlayerRegistrationMapping?: KeyBoundMappingResolver
}>

export type AckAdapterInjections = D1QueueTransitionInjections &
  KeyBoundMappingInjections &
  I6PersistenceInjections

function sameEventKey(first: QueueEventKey, second: QueueEventKey): boolean {
  return (
    Object.is(first.d4, second.d4) &&
    Object.is(first.d1, second.d1) &&
    Object.is(first.d5, second.d5)
  )
}

function eventKeyOf(result: D1AckEventResult): QueueEventKey {
  return { d4: result.d4, d1: result.d1, d5: result.d5 }
}

function eventResultFor(
  envelope: D1AckEnvelope,
  key: QueueEventKey,
): D1AckEventResult | undefined {
  return envelope.eventResults.find((result) =>
    sameEventKey(eventKeyOf(result), key),
  )
}

function mappingInjectionsFor(
  envelope: D1AckEnvelope,
  target: PlayerIdMappingTarget | undefined,
): KeyBoundMappingInjections {
  if (!target) {
    return Object.freeze({})
  }

  const eventResult = eventResultFor(envelope, target.key)
  const mappings = envelope.playerIdMappings?.filter((mapping) =>
    Object.is(mapping.temporaryId, target.temporaryId),
  )
  const reception = receivePlayerIdMapping({
    target,
    response:
      eventResult && mappings
        ? { key: eventKeyOf(eventResult), mappings }
        : undefined,
  })
  const resolver =
    reception.mappingConfirmation.resolvePlayerRegistrationMapping
  if (!resolver) {
    return Object.freeze({})
  }

  // この注入器は target.key の preparation 専用である。対象イベントは永続化境界で
  // 複製されるためイベントの同一性では結合できず、(D4, D1, D5) のキーで結合する
  // (敵対レビュー P1 — 引数を無視すると同じ注入で別イベントを同期済みにできる)。
  return Object.freeze({
    resolvePlayerRegistrationMapping: (input) =>
      sameEventKey(input.key, target.key) ? resolver(target.event) : undefined,
  })
}

function classificationInjectionsFor(
  envelope: D1AckEnvelope,
  boundaryResultId: string,
  rejection: B3Rejection | undefined,
): Pick<QueueTransitionInjections, 'classifyB3'> {
  if (boundaryResultId !== B3_BOUNDARY_RESULT_ID || !rejection) {
    return Object.freeze({})
  }

  const classifyB3: NonNullable<QueueTransitionInjections['classifyB3']> = (
    input,
  ) => {
    if (input.slot.source !== 'd1-event') {
      return undefined
    }
    const eventResult = eventResultFor(envelope, input.slot.key)
    if (!eventResult || !Object.is(eventResult.a5Result, input.result)) {
      return undefined
    }
    return { kind: rejection.kind }
  }
  return Object.freeze({ classifyB3 })
}

function d1InjectionsFor(
  input: D1AckAdapterInput | undefined,
): D1QueueTransitionInjections & KeyBoundMappingInjections {
  if (!input) {
    return Object.freeze({})
  }

  const envelope = parseD1AckEnvelope(input.envelope)
  const boundaryResult = parseAckBoundaryResult(input.boundaryResult)
  const rejection =
    boundaryResult.boundaryResult.id === B3_BOUNDARY_RESULT_ID &&
    input.b3Rejection !== undefined
      ? parseB3Rejection(input.b3Rejection)
      : undefined
  const resolveA5: NonNullable<QueueTransitionInjections['resolveA5']> = (
    key,
  ) => {
    const eventResult = eventResultFor(envelope, key)
    return eventResult
      ? { key: eventKeyOf(eventResult), result: eventResult.a5Result }
      : undefined
  }

  return Object.freeze({
    resolveA5,
    ...classificationInjectionsFor(
      envelope,
      boundaryResult.boundaryResult.id,
      rejection,
    ),
    ...mappingInjectionsFor(envelope, input.playerIdMappingTarget),
  })
}

function p3InjectionsFor(
  input: P3ResultAdapterInput | undefined,
): I6PersistenceInjections {
  if (!input) {
    return Object.freeze({})
  }

  const envelope = parseP3ResultEnvelope(input.envelope, input.expected)
  if (!('acceptedResult' in envelope)) {
    return Object.freeze({})
  }

  const resolveAcceptedAt: NonNullable<
    I6PersistenceInjections['resolveAcceptedAt']
  > = (acceptance): I6AcceptedAtResolution | undefined =>
    Object.is(acceptance, input.expected)
      ? {
          known: true,
          targetReference: envelope.acceptedResult.targetReference,
          acceptedAt: envelope.acceptedResult.acceptedAt,
        }
      : undefined

  return Object.freeze({ resolveAcceptedAt })
}

export function createAckAdapterInjections(
  request: AckAdapterRequest = {},
): AckAdapterInjections {
  return Object.freeze({
    ...d1InjectionsFor(request.d1),
    ...p3InjectionsFor(request.p3),
  })
}

// この封筒は docs/design/sync-protocol.md 7-1・7-2 の P3 独立応答を表す。
// サーバー側の判定・永続化・失われた結果の探索や回収は行わず、受け取った全組だけを検証する。

import {
  readCanonP3BoundaryResults,
  type CanonP3BoundaryResult,
} from './canonOracle'
import type { I6Acceptance, I6AcceptedResult } from './queueState'
import { assertExactDefinedObject } from './receptionInput'
import {
  isTargetEventReference,
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type TargetEventReference,
} from './syncEvent'

type AcceptedP3BoundaryResult = Extract<
  CanonP3BoundaryResult,
  { accepted: true }
>
type RejectedP3BoundaryResult = Extract<
  CanonP3BoundaryResult,
  { accepted: false }
>

export type P3AcceptedResultEnvelope = Readonly<{
  boundaryResult: AcceptedP3BoundaryResult
  acceptedResult: I6AcceptedResult
}>

export type P3RejectedResultEnvelope = Readonly<{
  boundaryResult: RejectedP3BoundaryResult
}>

export type P3ResultEnvelope =
  P3AcceptedResultEnvelope | P3RejectedResultEnvelope

const RESULT_ENVELOPE_KEYS = Object.freeze([
  'boundaryResult',
  'acceptedResult',
] as const)
const RESULT_REQUIRED_KEYS = Object.freeze(['boundaryResult'] as const)
const ACCEPTED_ENVELOPE_KEYS = RESULT_ENVELOPE_KEYS
const REJECTED_ENVELOPE_KEYS = RESULT_REQUIRED_KEYS
const ACCEPTANCE_KEYS = Object.freeze([
  'targetReference',
  'expectedVersion',
  'd5',
  'confirmedContent',
] as const)
const ACCEPTED_RESULT_KEYS = Object.freeze([
  ...ACCEPTANCE_KEYS,
  'acceptedAt',
] as const)

function sameTargetReference(
  first: TargetEventReference,
  second: TargetEventReference,
): boolean {
  return TARGET_EVENT_REFERENCE_ELEMENTS.every((element) =>
    Object.is(first[element], second[element]),
  )
}

function parseAcceptedResult(
  candidate: Record<PropertyKey, unknown>,
  boundaryResult: AcceptedP3BoundaryResult,
  expected: I6Acceptance,
): P3AcceptedResultEnvelope {
  assertExactDefinedObject(
    candidate,
    ACCEPTED_ENVELOPE_KEYS,
    ACCEPTED_ENVELOPE_KEYS,
    'P3 受理結果の封筒が完全ではありません',
  )
  const acceptedResult = candidate.acceptedResult
  assertExactDefinedObject(
    acceptedResult,
    ACCEPTED_RESULT_KEYS,
    ACCEPTED_RESULT_KEYS,
    'P3 受理結果の I6 全組（accepted_at を含む）が不足しているか、余分な要素があります',
  )
  assertExactDefinedObject(
    acceptedResult.targetReference,
    TARGET_EVENT_REFERENCE_ELEMENTS,
    TARGET_EVENT_REFERENCE_ELEMENTS,
    'P3 受理結果の対象参照が完全ではありません',
  )
  if (
    !isTargetEventReference(acceptedResult.targetReference) ||
    !sameTargetReference(
      acceptedResult.targetReference,
      expected.targetReference,
    )
  ) {
    throw new Error('P3 受理結果の対象参照が一致しません')
  }
  if (!Object.is(acceptedResult.d5, expected.d5)) {
    throw new Error('P3 受理結果の D5 が一致しません')
  }
  if (!Object.is(acceptedResult.expectedVersion, expected.expectedVersion)) {
    throw new Error('P3 受理結果の V11 が一致しません')
  }
  if (!Object.is(acceptedResult.confirmedContent, expected.confirmedContent)) {
    throw new Error('P3 受理結果の確定内容が一致しません')
  }
  return Object.freeze({
    boundaryResult,
    acceptedResult: Object.freeze({
      targetReference: acceptedResult.targetReference,
      expectedVersion: acceptedResult.expectedVersion,
      d5: acceptedResult.d5,
      confirmedContent: acceptedResult.confirmedContent,
      acceptedAt: acceptedResult.acceptedAt,
    }),
  })
}

export function parseP3ResultEnvelope(
  candidate: unknown,
  expected: I6Acceptance,
): P3ResultEnvelope {
  assertExactDefinedObject(
    candidate,
    RESULT_ENVELOPE_KEYS,
    RESULT_REQUIRED_KEYS,
    'P3 独立応答に境界結果がないか、余分な要素があります',
  )
  assertExactDefinedObject(
    expected,
    ACCEPTANCE_KEYS,
    ACCEPTANCE_KEYS,
    'P3 受理期待値の全組が不足しているか、余分な要素があります',
  )
  assertExactDefinedObject(
    expected.targetReference,
    TARGET_EVENT_REFERENCE_ELEMENTS,
    TARGET_EVENT_REFERENCE_ELEMENTS,
    'P3 受理期待値の対象参照が完全ではありません',
  )
  const boundaryResult = readCanonP3BoundaryResults().find((result) =>
    Object.is(result.id, candidate.boundaryResult),
  )
  if (!boundaryResult) {
    throw new Error('P3 独立応答に未知の境界結果があります')
  }

  if (boundaryResult.accepted) {
    return parseAcceptedResult(candidate, boundaryResult, expected)
  }
  assertExactDefinedObject(
    candidate,
    REJECTED_ENVELOPE_KEYS,
    REJECTED_ENVELOPE_KEYS,
    'P3 の拒否結果に I6 情報または余分な要素を指定できません',
  )
  return Object.freeze({ boundaryResult })
}

// この封筒は docs/design/sync-protocol.md 7-1・7-2 の P3 独立応答を表す。
// サーバー側の判定・永続化・失われた結果の探索や回収は行わず、受け取った全組だけを検証する。

import {
  readCanonP3BoundaryResults,
  type CanonP3BoundaryResult,
} from './canonOracle'
import type { I6Acceptance, I6AcceptedResult } from './queueState'
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

function isRecord(value: unknown): value is Record<PropertyKey, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasOwn(value: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, key)
}

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
  const acceptedResult = candidate.acceptedResult
  if (
    !isRecord(acceptedResult) ||
    !hasOwn(acceptedResult, 'targetReference') ||
    !hasOwn(acceptedResult, 'expectedVersion') ||
    !hasOwn(acceptedResult, 'd5') ||
    !hasOwn(acceptedResult, 'confirmedContent') ||
    !hasOwn(acceptedResult, 'acceptedAt')
  ) {
    throw new Error('P3 受理結果の I6 全組が不足しています')
  }
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
  if (acceptedResult.acceptedAt === undefined) {
    throw new Error('P3 受理結果に accepted_at がありません')
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
  if (!isRecord(candidate) || !hasOwn(candidate, 'boundaryResult')) {
    throw new Error('P3 独立応答に境界結果がありません')
  }
  const boundaryResult = readCanonP3BoundaryResults().find(
    (result) => result.id === candidate.boundaryResult,
  )
  if (!boundaryResult) {
    throw new Error('P3 独立応答に未知の境界結果があります')
  }

  if (boundaryResult.accepted) {
    return parseAcceptedResult(candidate, boundaryResult, expected)
  }
  if (hasOwn(candidate, 'acceptedResult')) {
    throw new Error('P3 の拒否結果に I6 情報を指定できません')
  }
  return Object.freeze({ boundaryResult })
}

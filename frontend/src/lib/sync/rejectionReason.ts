// この DTO とパーサは docs/design/sync-protocol.md 6-3・6-4・7-2 の B3 受け取り契約を表す。
// サーバーが返した区分だけを検証し、理由の内容や操作者が選ぶ再開方法は解釈しない。

import { assertExactDefinedObject } from './receptionInput'

export const B3_REJECTION_KIND = {
  CONTENT: '内容起因',
  O4: 'O4',
} as const

export const B3_CONTENT_BRANCH = {
  B3A: 'B3a',
  B3B: 'B3b',
} as const

export const O4_CORRECTION_CONFIRMATION = {
  PENDING: '管理者による是正確認待ち',
} as const

export type B3ContentBranch =
  (typeof B3_CONTENT_BRANCH)[keyof typeof B3_CONTENT_BRANCH]

export type B3ContentRejection = Readonly<{
  kind: typeof B3_REJECTION_KIND.CONTENT
  branch: B3ContentBranch
  reason: unknown
}>

export type B3O4Rejection = Readonly<{
  kind: typeof B3_REJECTION_KIND.O4
  reason: unknown
  correctionConfirmation: typeof O4_CORRECTION_CONFIRMATION.PENDING
}>

export type B3Rejection = B3ContentRejection | B3O4Rejection

const REJECTION_KEYS = Object.freeze(['kind', 'branch', 'reason'] as const)
const REJECTION_REQUIRED_KEYS = Object.freeze(['kind', 'reason'] as const)
const CONTENT_REJECTION_KEYS = REJECTION_KEYS
const O4_REJECTION_KEYS = Object.freeze(['kind', 'reason'] as const)

function parseContentRejection(
  candidate: Record<PropertyKey, unknown>,
): B3ContentRejection {
  assertExactDefinedObject(
    candidate,
    CONTENT_REJECTION_KEYS,
    CONTENT_REJECTION_KEYS,
    'B3 内容拒否の要素が不足しているか、余分な要素があります',
  )
  const branch = Object.values(B3_CONTENT_BRANCH).find((knownBranch) =>
    Object.is(knownBranch, candidate.branch),
  )
  if (!branch) {
    throw new Error('未知の B3 内容拒否区分です')
  }

  return Object.freeze({
    kind: B3_REJECTION_KIND.CONTENT,
    branch,
    reason: candidate.reason,
  })
}

export function parseB3Rejection(candidate: unknown): B3Rejection {
  assertExactDefinedObject(
    candidate,
    REJECTION_KEYS,
    REJECTION_REQUIRED_KEYS,
    'B3 の理由がありません',
  )

  if (Object.is(candidate.kind, B3_REJECTION_KIND.CONTENT)) {
    return parseContentRejection(candidate)
  }
  if (Object.is(candidate.kind, B3_REJECTION_KIND.O4)) {
    assertExactDefinedObject(
      candidate,
      O4_REJECTION_KEYS,
      O4_REJECTION_KEYS,
      'O4 に B3 内容拒否区分または余分な要素を指定できません',
    )
    return Object.freeze({
      kind: B3_REJECTION_KIND.O4,
      reason: candidate.reason,
      correctionConfirmation: O4_CORRECTION_CONFIRMATION.PENDING,
    })
  }

  throw new Error('未知の B3 分類です')
}

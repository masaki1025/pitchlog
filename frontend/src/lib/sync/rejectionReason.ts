// この DTO とパーサは docs/design/sync-protocol.md 6-3・6-4・7-2 の B3 受け取り契約を表す。
// サーバーが返した区分だけを検証し、理由の内容や操作者が選ぶ再開方法は解釈しない。

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

function isRecord(value: unknown): value is Record<PropertyKey, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function hasOwn(value: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(value, key)
}

function parseContentRejection(
  candidate: Record<PropertyKey, unknown>,
): B3ContentRejection {
  if (
    candidate.branch !== B3_CONTENT_BRANCH.B3A &&
    candidate.branch !== B3_CONTENT_BRANCH.B3B
  ) {
    throw new Error('未知の B3 内容拒否区分です')
  }

  return Object.freeze({
    kind: B3_REJECTION_KIND.CONTENT,
    branch: candidate.branch,
    reason: candidate.reason,
  })
}

export function parseB3Rejection(candidate: unknown): B3Rejection {
  if (!isRecord(candidate) || !hasOwn(candidate, 'reason')) {
    throw new Error('B3 の理由がありません')
  }

  if (candidate.kind === B3_REJECTION_KIND.CONTENT) {
    return parseContentRejection(candidate)
  }
  if (candidate.kind === B3_REJECTION_KIND.O4) {
    if (hasOwn(candidate, 'branch')) {
      throw new Error('O4 に B3 内容拒否区分を指定できません')
    }
    return Object.freeze({
      kind: B3_REJECTION_KIND.O4,
      reason: candidate.reason,
      correctionConfirmation: O4_CORRECTION_CONFIRMATION.PENDING,
    })
  }

  throw new Error('未知の B3 分類です')
}

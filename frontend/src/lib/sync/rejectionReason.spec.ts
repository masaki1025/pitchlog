import { describe, expect, it } from 'vitest'
import rejectionReasonSource from './rejectionReason.ts?raw'
import {
  B3_CONTENT_BRANCH,
  B3_REJECTION_KIND,
  O4_CORRECTION_CONFIRMATION,
  parseB3Rejection,
} from './rejectionReason'

describe('rejectionReason', () => {
  it.each(Object.values(B3_CONTENT_BRANCH))(
    '%s を内容起因のサーバー分類として区別したまま保持する',
    (branch) => {
      const reason = {}

      expect(
        parseB3Rejection({
          kind: B3_REJECTION_KIND.CONTENT,
          branch,
          reason,
        }),
      ).toEqual({ kind: B3_REJECTION_KIND.CONTENT, branch, reason })
    },
  )

  it('reason の文言が異なっても受け取った区分を変えない', () => {
    const first = parseB3Rejection({
      kind: B3_REJECTION_KIND.CONTENT,
      branch: B3_CONTENT_BRANCH.B3A,
      reason: '墓標を連想させる文言',
    })
    const second = parseB3Rejection({
      kind: B3_REJECTION_KIND.CONTENT,
      branch: B3_CONTENT_BRANCH.B3A,
      reason: '改訂を連想させる文言',
    })

    expect(first.kind).toBe(second.kind)
    if (
      first.kind !== B3_REJECTION_KIND.CONTENT ||
      second.kind !== B3_REJECTION_KIND.CONTENT
    ) {
      throw new Error('内容起因の分類が保持されていません')
    }
    expect(first.branch).toBe(second.branch)
    expect(first.reason).not.toBe(second.reason)
  })

  it('reason を不透明値として保持し、内部を検査しない', () => {
    const reason = new Proxy(
      {},
      {
        get() {
          throw new Error('reason の内部を読みました')
        },
        ownKeys() {
          throw new Error('reason の内部キーを読みました')
        },
      },
    )

    const parsed = parseB3Rejection({
      kind: B3_REJECTION_KIND.CONTENT,
      branch: B3_CONTENT_BRANCH.B3B,
      reason,
    })

    expect(parsed.reason).toBe(reason)
  })

  it('O4 を管理者による是正確認待ちとして区別する', () => {
    const reason = {}

    expect(parseB3Rejection({ kind: B3_REJECTION_KIND.O4, reason })).toEqual({
      kind: B3_REJECTION_KIND.O4,
      reason,
      correctionConfirmation: O4_CORRECTION_CONFIRMATION.PENDING,
    })
  })

  it('未知の内容拒否区分を fail-closed に拒否する', () => {
    expect(() =>
      parseB3Rejection({
        kind: B3_REJECTION_KIND.CONTENT,
        branch: 'B3c',
        reason: {},
      }),
    ).toThrowError(/未知の B3 内容拒否区分/)
  })

  it('未知の B3 分類を fail-closed に拒否する', () => {
    expect(() =>
      parseB3Rejection({ kind: '未知の分類', reason: {} }),
    ).toThrowError(/未知の B3 分類/)
  })

  it('reason の欠落を fail-closed に拒否する', () => {
    expect(() =>
      parseB3Rejection({
        kind: B3_REJECTION_KIND.CONTENT,
        branch: B3_CONTENT_BRANCH.B3A,
      }),
    ).toThrowError(/理由がありません/)
  })

  it('reason が undefined の拒否結果を fail-closed に拒否する', () => {
    expect(() =>
      parseB3Rejection({
        kind: B3_REJECTION_KIND.CONTENT,
        branch: B3_CONTENT_BRANCH.B3A,
        reason: undefined,
      }),
    ).toThrowError(/理由がありません/)
  })

  it.each([
    {
      kind: B3_REJECTION_KIND.CONTENT,
      branch: B3_CONTENT_BRANCH.B3A,
      reason: {},
      extra: {},
    },
    { kind: B3_REJECTION_KIND.O4, reason: {}, extra: {} },
  ])('余分なキーを持つ拒否結果を拒否する', (candidate) => {
    expect(() => parseB3Rejection(candidate)).toThrow()
  })

  it('O4 に内容拒否の下位区分を混在させない', () => {
    expect(() =>
      parseB3Rejection({
        kind: B3_REJECTION_KIND.O4,
        branch: B3_CONTENT_BRANCH.B3A,
        reason: {},
      }),
    ).toThrowError(/指定できません/)
  })

  it('reason の文言を条件式・switch・正規表現の対象にしない', () => {
    expect(rejectionReasonSource).not.toMatch(/if\s*\([^)]*\.reason/)
    expect(rejectionReasonSource).not.toMatch(/switch\s*\([^)]*\.reason/)
    expect(rejectionReasonSource).not.toMatch(
      /\.reason\s*\.\s*(?:includes|match|search|startsWith|endsWith|test)\s*\(/,
    )
    expect(rejectionReasonSource).not.toMatch(/RegExp/)
  })

  it('操作者が選ぶ要操作ラベルを製品コードに持たない', () => {
    const forbiddenLabelLiterals = ['改訂待ち', '墓標待ち']

    for (const label of forbiddenLabelLiterals) {
      expect(rejectionReasonSource).not.toContain(`'${label}'`)
      expect(rejectionReasonSource).not.toContain(`"${label}"`)
    }
    expect(rejectionReasonSource).not.toMatch(/actionRequiredLabel/)
  })
})

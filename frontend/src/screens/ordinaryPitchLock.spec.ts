import { describe, expect, it } from 'vitest'
import { ordinaryPitchLockReason } from './ordinaryPitchLock'

describe('通常球入力の停止理由', () => {
  it('タイブレーク開始要求を終了条件より先に返す', () => {
    expect(
      ordinaryPitchLockReason({
        tiebreakStartRequired: true,
        decision: { lockFurtherPlayInput: true },
      }),
    ).toBe('tiebreak')
  })

  it('終了条件のロックだけをendとして返す', () => {
    expect(
      ordinaryPitchLockReason({
        tiebreakStartRequired: false,
        decision: { lockFurtherPlayInput: true },
      }),
    ).toBe('end')
  })

  it('未ロック・欠落・不正形を停止理由にしない', () => {
    expect(
      ordinaryPitchLockReason({
        tiebreakStartRequired: false,
        decision: { lockFurtherPlayInput: false },
      }),
    ).toBeNull()
    expect(ordinaryPitchLockReason(null)).toBeNull()
    expect(ordinaryPitchLockReason('locked')).toBeNull()
  })
})

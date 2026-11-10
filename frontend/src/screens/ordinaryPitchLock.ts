/** 通常球入力の停止理由を、保存済みT2の閉値だけから導く。 */
export type OrdinaryPitchLock = 'end' | 'tiebreak'

export function ordinaryPitchLockReason(
  value: unknown,
): OrdinaryPitchLock | null {
  if (value === null || typeof value !== 'object') return null
  const t2 = value as {
    tiebreakStartRequired?: unknown
    decision?: { lockFurtherPlayInput?: unknown }
  }
  if (t2.tiebreakStartRequired === true) return 'tiebreak'
  if (t2.decision?.lockFurtherPlayInput === true) return 'end'
  return null
}

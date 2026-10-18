/** 認証以外の単体試験へ、検証成功後のstoreを準備する。製品からimportしない。 */
import { vi } from 'vitest'
import type { useAuthStore } from '../stores/authStore'
import { withAuthIntent, writeAuthIntent } from './authIntent'

type Auth = ReturnType<typeof useAuthStore>
export function setVerifiedAuthForTest(
  auth: Auth,
  team: { teamName: string; teamId?: string | null },
): void {
  if (!navigator.locks?.request) {
    vi.stubGlobal('navigator', {
      locks: {
        request: vi.fn(async (_name, _options, callback) =>
          callback({ name: 'unit-fixture' }),
        ),
      },
    })
  }
  let completed = false
  let failure: unknown
  // これは同期fake lockを使う単体fixture。native lockの受入を代替しない。
  void withAuthIntent(() => {
    try {
      const id = team.teamId ?? '11111111-1111-4111-8111-111111111111'
      const marker = writeAuthIntent('expected', id)
      auth.beginCorrelatedVerification(marker.intentId)
      auth.adoptCorrelatedSession(marker.intentId, id, team.teamName, null)
    } catch (error) {
      failure = error
    }
    completed = true
  }).catch(() => undefined)
  if (!completed) throw new Error('単体fixtureには同期fake lockが必要です')
  if (failure) throw failure
}

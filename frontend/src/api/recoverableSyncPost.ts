import { SyncAttemptBarrier } from '../lib/syncAttemptBarrier'
import { useAuthStore } from '../stores/authStore'
import { apiRequest, type SyncRequestCredentials } from './client'
import { recoverSyncAttempt } from './syncAttemptRecovery'

/** 実E-1の全入口へ同じ耐久試行バリアと権威照会を適用する。 */
export async function postRecoverableSyncRequest<TBody>(
  gameId: string,
  body: TBody,
  credentials?: SyncRequestCredentials,
): Promise<{ body: TBody; response: unknown }> {
  let current = credentials
  let original = body
  if (current !== undefined) {
    const auth = useAuthStore()
    if (!auth.isAuthenticated || auth.teamId === null)
      throw new Error('元試行の認証を確認できません')
    const barrier = await SyncAttemptBarrier.open()
    try {
      const prepared = await barrier.prepare(
        auth.teamId,
        gameId,
        body,
        current.deviceId,
        current.attempt,
      )
      original = JSON.parse(prepared.barrier.bodyJson) as TBody
      if (!prepared.created) {
        const resolution = await recoverSyncAttempt(gameId, original, {
          ...current,
          attempt: prepared.barrier.currentAttemptId,
        })
        if (resolution !== 'retry_allowed')
          throw new Error('旧試行の終結を確認できません')
        const nextAttemptId = crypto.randomUUID()
        await barrier.advance(prepared.barrier, nextAttemptId)
        current = { ...current, attempt: nextAttemptId }
      }
    } finally {
      barrier.close()
    }
  }
  const response = await apiRequest<unknown>(
    'POST',
    `/games/${encodeURIComponent(gameId)}/sync/events`,
    {
      tenantBound: true,
      body: original,
      ...(current === undefined ? {} : { syncCredentials: current }),
    },
  )
  return { body: original, response }
}

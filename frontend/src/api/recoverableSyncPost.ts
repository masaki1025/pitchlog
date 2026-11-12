import { SyncAttemptBarrier } from '../lib/syncAttemptBarrier'
import { useAuthStore } from '../stores/authStore'
import { apiRequest, type SyncRequestCredentials } from './client'
import { recoverSyncAttempt } from './syncAttemptRecovery'

export type RecoverableSyncOptions = Readonly<{
  /** 呼出元が権威照会と後着遮断を済ませた場合だけ、同じ本文の送信へ進む。 */
  skipRecovery?: boolean
  signal?: AbortSignal
}>

/** 実E-1の全入口へ同じ耐久試行バリアと権威照会を適用する。 */
export async function postRecoverableSyncRequest<TBody>(
  gameId: string,
  body: TBody,
  credentials?: SyncRequestCredentials,
  options: RecoverableSyncOptions = {},
): Promise<{ body: TBody; response: unknown }> {
  return postOriginal(gameId, body, credentials, 'events', options)
}

/** P3専用入口。D1付きeventsへ変換せず元changeを保存・再送する。 */
export async function postRecoverableP3Change<TBody>(
  gameId: string,
  body: TBody,
  credentials: SyncRequestCredentials,
): Promise<{ body: TBody; response: unknown }> {
  return postOriginal(gameId, body, credentials, 'change')
}

async function postOriginal<TBody>(
  gameId: string,
  body: TBody,
  credentials: SyncRequestCredentials | undefined,
  endpoint: 'events' | 'change',
  options: RecoverableSyncOptions = {},
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
      const isChange = Object.prototype.hasOwnProperty.call(original, 'change')
      if (isChange !== (endpoint === 'change'))
        throw new Error('元要求と同期入口が一致しません')
      if (!prepared.created) {
        if (options.skipRecovery) {
          // 直前に同じ本文を照会し、後着遮断と次attemptの固定を済ませている。
          current = { ...current, attempt: prepared.barrier.currentAttemptId }
        } else {
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
      } else if (options.skipRecovery) {
        throw new Error('照会済みの試行バリアを確認できません')
      }
    } finally {
      barrier.close()
    }
  }
  const response = await apiRequest<unknown>(
    'POST',
    `/games/${encodeURIComponent(gameId)}/sync/${endpoint}`,
    {
      tenantBound: true,
      body: original,
      ...(current === undefined ? {} : { syncCredentials: current }),
      ...(options.signal === undefined ? {} : { signal: options.signal }),
    },
  )
  return { body: original, response }
}

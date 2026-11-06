import { apiRequest, type SyncRequestCredentials } from './client'

export type AttemptRecoveryResolution = 'retry_allowed' | 'unresolved'

/** 元本文を変更せず、同じ実認証/C2/端末資格で旧attemptだけを照会する。 */
export async function recoverSyncAttempt(
  gameId: string,
  originalBody: unknown,
  credentials: SyncRequestCredentials,
): Promise<AttemptRecoveryResolution> {
  const response: unknown = await apiRequest<unknown>(
    'POST',
    `/games/${encodeURIComponent(gameId)}/sync/attempts/recover`,
    {
      tenantBound: true,
      body: originalBody,
      syncCredentials: credentials,
    },
  )
  if (
    response === null ||
    typeof response !== 'object' ||
    Array.isArray(response) ||
    Object.keys(response).sort().join(',') !== 'resolution'
  )
    throw new Error('旧試行の照会結果を確認できません')
  const resolution = (response as Record<string, unknown>).resolution
  if (resolution !== 'retry_allowed' && resolution !== 'unresolved')
    throw new Error('旧試行の照会結果を確認できません')
  return resolution
}

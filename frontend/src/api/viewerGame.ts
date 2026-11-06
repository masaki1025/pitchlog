/** 閲覧用の軽量版照会と、版変更時だけ使う既閉GET。 */
import { ApiError, apiRequest } from './client'
import { canonicalUuid } from './authIntent'
import { isLineupPrefixGame, type LineupPrefixGame } from './lineupPrefixGame'
import { isGameLifecycleGame, type GameLifecycleGame } from './gameLifecycle'
import { exactPlayObject } from './terminalPitchWire'

export type ViewerHead = Readonly<{
  status: 'in_progress' | 'finished'
  generation: string
  watermark: string
}>
export type ViewerLineupPrefixGame = Omit<LineupPrefixGame, 'status'> &
  Readonly<{ status: 'in_progress' | 'finished' }>
export type ViewerGame = ViewerLineupPrefixGame | GameLifecycleGame
const positive = (value: unknown): value is string =>
  typeof value === 'string' && /^[1-9][0-9]*$/.test(value)
const unsigned = (value: unknown): value is string =>
  value === '0' || positive(value)

export function isViewerHead(value: unknown): value is ViewerHead {
  return (
    exactPlayObject(value, ['status', 'generation', 'watermark']) &&
    (value.status === 'in_progress' || value.status === 'finished') &&
    positive(value.generation) &&
    unsigned(value.watermark)
  )
}

/** 記録用DTOは進行中限定。閲覧の終了版は同じ全項目を閉検査する。 */
export function isViewerLineupPrefixGame(
  value: unknown,
): value is ViewerLineupPrefixGame {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return false
  const row = value as Record<string, unknown>
  if (row.status === 'in_progress') return isLineupPrefixGame(value)
  if (row.status !== 'finished') return false
  return isLineupPrefixGame({ ...row, status: 'in_progress' })
}

/** 認証済み同tenantの非ロック版hint。保存内容の原本には使わない。 */
export async function readViewerHead(
  gameId: string,
  signal?: AbortSignal,
): Promise<ViewerHead> {
  if (!canonicalUuid.test(gameId)) throw new Error('閲覧対象を確認できません')
  const value = await apiRequest<unknown>(
    'GET',
    `/games/${gameId}/viewer-head`,
    { tenantBound: true, signal },
  )
  if (!isViewerHead(value)) throw new Error('閲覧版の応答が不正です')
  return value
}

/** RR READ ONLYの専用本体GETを閉codecで読み、同版を照合する。 */
export async function readViewerGame(
  gameId: string,
  tenantId: string,
  head: ViewerHead,
  cursor: string | null = null,
  signal?: AbortSignal,
): Promise<ViewerGame> {
  if (!canonicalUuid.test(gameId) || !canonicalUuid.test(tenantId))
    throw new Error('閲覧scopeを確認できません')
  if (!isViewerHead(head)) throw new Error('閲覧版の応答が不正です')
  if (cursor !== null && (cursor.length === 0 || cursor.length > 2048))
    throw new Error('閲覧cursorが不正です')
  const value = await apiRequest<unknown>('GET', `/games/${gameId}/viewer`, {
    tenantBound: true,
    query: { limit: 25, ...(cursor === null ? {} : { cursor }) },
    signal,
  })
  if (
    isViewerLineupPrefixGame(value) &&
    value.id === gameId &&
    value.prefix_ref.tenantId === tenantId &&
    value.status === head.status &&
    value.prefix_ref.length === head.watermark
  )
    return value
  if (
    isGameLifecycleGame(value) &&
    value.id === gameId &&
    value.checkpoint.content.scope.tenantId === tenantId &&
    value.status === head.status &&
    value.checkpoint.content.d3 === head.watermark
  )
    return value
  throw new Error('保存済み表示と閲覧版が一致しません')
}

/** 不可視・認証失効・一時失敗をFEで同じ古値成功にしない。 */
export function viewerFailure(error: unknown): 'not-found' | 'unupdated' {
  return error instanceof ApiError && error.status === 404
    ? 'not-found'
    : 'unupdated'
}

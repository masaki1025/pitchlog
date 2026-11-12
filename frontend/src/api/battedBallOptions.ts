import { apiRequest } from './client'
export type BattedBallOption = Readonly<{ key: string; display_name: string }>
export type BattedBallPage = Readonly<{
  items: readonly BattedBallOption[]
  next_cursor: string | null
}>
function invalid(): never {
  throw new Error('打球語彙の選択肢を確認できません')
}

// 同一tenant/epochの間だけ先頭ページを再利用する。ページ再読込で消える。
const firstPageCache = new Map<string, BattedBallPage>()
export function cachedBattedBallOptions(key: string): BattedBallPage | null {
  return firstPageCache.get(key) ?? null
}
export function rememberBattedBallOptions(
  key: string,
  page: BattedBallPage,
): void {
  if (page.next_cursor === null) firstPageCache.set(key, page)
}
export function clearBattedBallOptionsCache(): void {
  firstPageCache.clear()
}
/** 実tenant限定の1ページだけを読む。全件読み込み・固定語彙補完はしない。 */
export async function readBattedBallOptions(
  cursor: string | null = null,
  limit = 25,
  signal?: AbortSignal,
): Promise<BattedBallPage> {
  if (
    !Number.isSafeInteger(limit) ||
    limit < 1 ||
    limit > 100 ||
    (cursor !== null && (typeof cursor !== 'string' || cursor.length === 0))
  )
    return invalid()
  const response: unknown = await apiRequest(
    'GET',
    '/vocabularies/batted-balls',
    {
      tenantBound: true,
      query: { limit, ...(cursor === null ? {} : { cursor }) },
      signal,
    },
  )
  if (
    typeof response !== 'object' ||
    response === null ||
    Array.isArray(response)
  )
    return invalid()
  const p = response as Record<string, unknown>
  if (
    Object.keys(p).sort().join(',') !== 'items,next_cursor' ||
    !Array.isArray(p.items) ||
    p.items.length > limit ||
    (p.next_cursor !== null &&
      (typeof p.next_cursor !== 'string' || p.next_cursor.length === 0))
  )
    return invalid()
  const seen = new Set<string>()
  const items: BattedBallOption[] = []
  for (const item of p.items) {
    if (typeof item !== 'object' || item === null || Array.isArray(item))
      return invalid()
    const value = item as Record<string, unknown>
    if (
      Object.keys(value).sort().join(',') !== 'display_name,key' ||
      typeof value.key !== 'string' ||
      value.key.length === 0 ||
      typeof value.display_name !== 'string' ||
      value.display_name.length === 0 ||
      seen.has(value.key)
    )
      return invalid()
    items.push({ key: value.key, display_name: value.display_name })
    seen.add(value.key)
  }
  if (
    p.next_cursor !== null &&
    (items.length === 0 || p.next_cursor === cursor)
  )
    return invalid()
  return { items, next_cursor: p.next_cursor as string | null }
}

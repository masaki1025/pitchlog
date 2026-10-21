import { canonicalUuid } from '../api/authIntent'

/** 認証前に保持できる登録済みの内部pathnameだけを返す。 */
export function resolveGameEntryReturnPath(value: unknown): string {
  if (value === '/team' || value === '/games') return value
  if (typeof value !== 'string') return '/team'
  const match = /^\/games\/([^/]+)\/record$/.exec(value)
  return match && canonicalUuid.test(match[1] ?? '') ? value : '/team'
}

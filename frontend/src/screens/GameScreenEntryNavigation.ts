import { canonicalUuid } from '../api/authIntent'

/** 認証前に保持できる登録済みの内部pathnameと有限な記録・閲覧入口だけを返す。 */
export function resolveGameEntryReturnPath(value: unknown): string {
  if (value === '/team' || value === '/games') return value
  if (typeof value !== 'string') return '/team'
  const match =
    /^\/games\/([^/]+)\/(?:view|record(?:\?recording=(?:ordinary-prefix-v1|play-prefix-v2|play-prefix-v3))?)$/.exec(
      value,
    )
  return match && canonicalUuid.test(match[1] ?? '') ? value : '/team'
}

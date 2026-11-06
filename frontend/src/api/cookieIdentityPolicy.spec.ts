import { describe, expect, it } from 'vitest'
import policy from '../../../contracts/authentication/cookie_identity_v1.json'
import { hasSameTokenCookiePolicy } from './cookieIdentityPolicy'

const id = '33333333-3333-4333-8333-333333333333'
describe('同提示token更新routeの閉宣言', () => {
  it.each(policy.operations)(
    '$operationId の実method/pathだけを選ぶ',
    (row) => {
      const path = row.path.replace(/\{[a-z_]+(?::uuid)?\}/g, id)
      expect(hasSameTokenCookiePolicy(row.method, path)).toBe(true)
      expect(hasSameTokenCookiePolicy(row.method, path + '/')).toBe(false)
      expect(hasSameTokenCookiePolicy(row.method, path + '/unknown')).toBe(
        false,
      )
    },
  )
  it.each([
    '/auth/login',
    '/auth/logout',
    '/auth/session',
    '/auth/password',
    '/gamesx',
    '/games/INVALID/started',
    '/games/%33' + id.slice(1) + '/started',
  ])('%s を宣言済みへ補修しない', (path) => {
    expect(hasSameTokenCookiePolicy('GET', path)).toBe(false)
  })
  it('未知のmethodを補修しない', () => {
    expect(hasSameTokenCookiePolicy('get', '/games')).toBe(false)
    expect(hasSameTokenCookiePolicy('DELETE', '/games')).toBe(false)
  })
})

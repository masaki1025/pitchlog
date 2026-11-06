/** サーバーと共有する同提示token更新宣言。認証の証拠としては使わない。 */
import policy from '../../../contracts/authentication/cookie_identity_v1.json'
import { canonicalUuid } from './authIntent'

type Operation = Readonly<{ operationId: string; method: string; path: string }>

/** 宣言の拡張や重複を黙って失効除外へ取り込まない。 */
function operations(value: unknown): readonly Operation[] {
  if (value === null || typeof value !== 'object')
    throw new Error('Cookie policyが不正です')
  const root = value as Record<string, unknown>
  if (
    Object.keys(root).sort().join(',') !==
      'operations,schemaVersion,semantics' ||
    root.schemaVersion !== 1 ||
    root.semantics !== 'same-presented-token-renewal-only' ||
    !Array.isArray(root.operations) ||
    root.operations.length === 0
  )
    throw new Error('Cookie policyの閉形式が不正です')
  const ids = new Set<string>(),
    routes = new Set<string>()
  return root.operations.map((value: unknown) => {
    if (value === null || typeof value !== 'object')
      throw new Error('Cookie操作が不正です')
    const row = value as Record<string, unknown>
    if (
      Object.keys(row).sort().join(',') !== 'method,operationId,path' ||
      typeof row.operationId !== 'string' ||
      !/^[a-z][a-z0-9_]*$/.test(row.operationId) ||
      typeof row.method !== 'string' ||
      !['GET', 'POST', 'PATCH', 'DELETE'].includes(row.method) ||
      typeof row.path !== 'string' ||
      !/^(?:\/[a-z0-9-]+|\/\{[a-z_]+(?::uuid)?\})+$/.test(row.path) ||
      row.path.startsWith('/auth/') ||
      ids.has(row.operationId) ||
      routes.has(row.method + ' ' + row.path)
    )
      throw new Error('Cookie操作が不正又は重複です')
    ids.add(row.operationId)
    routes.add(row.method + ' ' + row.path)
    return Object.freeze({
      operationId: row.operationId,
      method: row.method,
      path: row.path,
    })
  })
}

const declared = Object.freeze(operations(policy))

/** method/全pathと正準UUID変数が一致する既登録routeだけを選ぶ。 */
export function hasSameTokenCookiePolicy(
  method: string,
  path: string,
): boolean {
  const actual = path.split('/')
  return declared.some((operation) => {
    if (operation.method !== method) return false
    const template = operation.path.split('/')
    return (
      template.length === actual.length &&
      template.every((part, index) =>
        part.startsWith('{')
          ? canonicalUuid.test(actual[index] ?? '')
          : part === actual[index],
      )
    )
  })
}

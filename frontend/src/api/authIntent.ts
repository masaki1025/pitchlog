/** 保存値は認証の証拠ではなく、サーバー応答を採用するための相関制約。 */
export const AUTH_INTENT_KEY = 'bb.auth.intent'
export const AUTH_INTENT_LOCK = 'pitchlog.auth.intent'
let intentLockHeld = false

/** 同期排他callback外から検証済み状態を作らない。 */
export function assertAuthIntentLockHeld(): void {
  if (!intentLockHeld) throw new Error('認証意図lock外で採用できません')
}

export const canonicalUuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
export type AuthIntent = {
  version: 1
  intentId: string
  phase: 'pending' | 'expected' | 'verification-required' | 'signed-out'
  tenantId: string | null
}
export type AuthEnvironmentReason =
  | 'storage-unavailable'
  | 'lock-unavailable'
  | 'lock-busy'
  | 'identity-unavailable'

export class AuthEnvironmentError extends Error {
  readonly reason: AuthEnvironmentReason
  constructor(reason: AuthEnvironmentReason) {
    super(reason)
    this.reason = reason
    this.name = 'AuthEnvironmentError'
  }
}

export function readAuthIntent(): AuthIntent | null {
  let raw: string | null
  try {
    raw = localStorage.getItem(AUTH_INTENT_KEY)
  } catch {
    throw new AuthEnvironmentError('storage-unavailable')
  }
  if (raw === null || raw.length > 1024) return null
  try {
    const v: unknown = JSON.parse(raw)
    if (typeof v !== 'object' || v === null || Array.isArray(v)) return null
    const a = v as Record<string, unknown>
    if (
      Object.keys(a).length !== 4 ||
      a.version !== 1 ||
      typeof a.intentId !== 'string' ||
      !canonicalUuid.test(a.intentId) ||
      typeof a.phase !== 'string' ||
      !['pending', 'expected', 'verification-required', 'signed-out'].includes(
        String(a.phase),
      )
    )
      return null
    if (a.phase === 'expected') {
      if (typeof a.tenantId !== 'string' || !canonicalUuid.test(a.tenantId))
        return null
    } else if (a.phase === 'verification-required') {
      if (
        a.tenantId !== null &&
        (typeof a.tenantId !== 'string' || !canonicalUuid.test(a.tenantId))
      )
        return null
    } else if (a.tenantId !== null) return null
    return a as AuthIntent
  } catch {
    return null
  }
}

/** 排他中に通信や別lockの待機を入れない。取得できない場合は自動再試行しない。 */
export async function withAuthIntent<T>(
  action: (value: AuthIntent | null) => T,
): Promise<T> {
  if (!navigator.locks?.request)
    throw new AuthEnvironmentError('lock-unavailable')
  if (typeof globalThis.crypto?.randomUUID !== 'function')
    throw new AuthEnvironmentError('identity-unavailable')
  let result: { ok: true; value: T } | { ok: false; error: unknown }
  try {
    result = await navigator.locks.request(
      AUTH_INTENT_LOCK,
      { mode: 'exclusive', ifAvailable: true },
      (lock) => {
        if (!lock) throw new AuthEnvironmentError('lock-busy')
        intentLockHeld = true
        try {
          return { ok: true as const, value: action(readAuthIntent()) }
        } catch (error) {
          return { ok: false as const, error }
        } finally {
          intentLockHeld = false
        }
      },
    )
  } catch (error) {
    if (error instanceof AuthEnvironmentError) throw error
    throw new AuthEnvironmentError('lock-unavailable')
  }
  // actionの実装例外を「Web Locks非対応」に読み替えない。
  if (!result.ok) throw result.error
  return result.value
}

/** withAuthIntentの同期callbackからだけ呼ぶ。書込後も一致を確認する。 */
export function writeAuthIntent(
  phase: AuthIntent['phase'],
  tenantId: string | null,
): AuthIntent {
  assertAuthIntentLockHeld()
  const next: AuthIntent = {
    version: 1,
    intentId: crypto.randomUUID(),
    phase,
    tenantId,
  }
  try {
    localStorage.setItem(AUTH_INTENT_KEY, JSON.stringify(next))
    if (readAuthIntent()?.intentId !== next.intentId) throw new Error('changed')
  } catch {
    throw new AuthEnvironmentError('storage-unavailable')
  }
  return next
}

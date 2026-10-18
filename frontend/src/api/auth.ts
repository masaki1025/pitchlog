import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import {
  AuthEnvironmentError,
  canonicalUuid,
  withAuthIntent,
  writeAuthIntent,
  type AuthIntent,
} from './authIntent'
import { ApiError, ApiStaleAuthError, apiRequest } from './client'

/** 状態と世代は一緒に扱い、旧操作の表示結果を新しい画面へ渡さない。 */
export type SessionResult =
  | {
      status: 'authenticated'
      authEpoch: number
      tenantId: string
      teamName: string
    }
  | {
      status: 'server-unauthenticated' | 'verification-unknown' | 'stale'
      authEpoch: number
    }
export type LoginResult =
  SessionResult | { status: 'rejected'; authEpoch: number; httpStatus: number }
export type LogoutResult = {
  status: 'logged-out' | 'verification-unknown' | 'stale'
  authEpoch: number
}
type AuthStore = ReturnType<typeof useAuthStore>
type Pending<T> = { epoch: number; promise: Promise<T> }
const sessions = new WeakMap<AuthStore, Pending<SessionResult>>()
const lastChecks = new WeakMap<AuthStore, SessionResult>()
const mutations = new WeakMap<AuthStore, { epoch: number }>()

export class AuthOperationInProgressError extends Error {
  constructor() {
    super('認証操作が進行中です')
    this.name = 'AuthOperationInProgressError'
  }
}

function store(): AuthStore {
  const pinia = getActivePinia()
  if (!pinia) throw new Error('Pinia が未インストールです')
  const auth = useAuthStore(pinia)
  auth.syncFromStorage()
  return auth
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function authenticated(auth: AuthStore): SessionResult {
  return {
    status: 'authenticated',
    authEpoch: auth.authEpoch,
    tenantId: auth.teamId!,
    teamName: auth.teamName!,
  }
}
function unknown(auth: AuthStore): {
  status: 'verification-unknown'
  authEpoch: number
} {
  const result = {
    status: 'verification-unknown' as const,
    authEpoch: auth.authEpoch,
  }
  lastChecks.set(auth, result)
  return result
}
function failedEnvironment(
  auth: AuthStore,
  error: unknown,
): { status: 'verification-unknown'; authEpoch: number } {
  if (error instanceof AuthEnvironmentError)
    auth.failAuthEnvironment(error.reason)
  else {
    auth.beginCorrelatedVerification(null)
    auth.requireExplicitLogin()
  }
  return unknown(auth)
}
function pendingMutation(auth: AuthStore): boolean {
  return mutations.get(auth)?.epoch === auth.authEpoch
}

/** 旧Cookieの変更可能性だけを通知し、旧応答のID・成功状態は採用しない。 */
async function invalidateCookieUncertainty(auth: AuthStore): Promise<void> {
  try {
    await withAuthIntent((now) => {
      // 同一の未確認意図を重複破棄・通知しない。
      const marker =
        now?.phase === 'verification-required'
          ? now
          : writeAuthIntent('verification-required', now?.tenantId ?? null)
      auth.observeUnconfirmedIntent(marker.intentId)
      unknown(auth)
    })
  } catch (error) {
    failedEnvironment(auth, error)
  }
}

async function markUnknown(
  auth: AuthStore,
  intent: AuthIntent,
  epoch: number,
): Promise<SessionResult> {
  try {
    return await withAuthIntent((now) => {
      auth.syncFromStorage()
      if (now?.intentId !== intent.intentId || auth.authEpoch !== epoch)
        return { status: 'stale' as const, authEpoch: epoch }
      const next = writeAuthIntent('verification-required', intent.tenantId)
      auth.beginCorrelatedVerification(next.intentId)
      return unknown(auth)
    })
  } catch (error) {
    return failedEnvironment(auth, error)
  }
}

async function readSession(
  auth: AuthStore,
  intent: AuthIntent,
  epoch: number,
  signal?: AbortSignal,
): Promise<SessionResult> {
  try {
    const value = await apiRequest<unknown>('GET', '/auth/session', {
      noAuthExpiry: true,
      signal,
    })
    let stale = false
    const result = await withAuthIntent((now) => {
      auth.syncFromStorage()
      if (now?.intentId !== intent.intentId || auth.authEpoch !== epoch) {
        stale = true
        return { status: 'stale' as const, authEpoch: epoch }
      }
      if (
        !object(value) ||
        Object.keys(value).length !== 2 ||
        typeof value.tenant_id !== 'string' ||
        !canonicalUuid.test(value.tenant_id) ||
        typeof value.team_name !== 'string' ||
        value.team_name.length === 0 ||
        value.tenant_id !== intent.tenantId
      ) {
        const next = writeAuthIntent('verification-required', intent.tenantId)
        auth.beginCorrelatedVerification(next.intentId)
        return unknown(auth)
      }
      // expectedへ戻すのは明示再確認に成功した時だけ。通常GETでは共有値を更新しない。
      const marker =
        now.phase === 'expected'
          ? now
          : writeAuthIntent('expected', intent.tenantId)
      if (marker.intentId !== now.intentId)
        auth.observeUnconfirmedIntent(marker.intentId)
      auth.adoptCorrelatedSession(
        marker.intentId,
        value.tenant_id,
        value.team_name,
      )
      return authenticated(auth)
    })
    if (stale) await invalidateCookieUncertainty(auth)
    return result
  } catch (error) {
    if (error instanceof AuthEnvironmentError)
      return failedEnvironment(auth, error)
    if (error instanceof ApiStaleAuthError) {
      if (error.status !== 401) await invalidateCookieUncertainty(auth)
      return { status: 'stale', authEpoch: epoch }
    }
    if (error instanceof ApiError && error.status === 401) {
      try {
        return await withAuthIntent((now) => {
          auth.syncFromStorage()
          if (now?.intentId !== intent.intentId || auth.authEpoch !== epoch)
            return { status: 'stale' as const, authEpoch: epoch }
          const next = writeAuthIntent('signed-out', null)
          auth.beginCorrelatedVerification(next.intentId)
          const result = {
            status: 'server-unauthenticated' as const,
            authEpoch: auth.authEpoch,
          }
          lastChecks.set(auth, result)
          return result
        })
      } catch (failure) {
        return failedEnvironment(auth, failure)
      }
    }
    // sessionは401以外の失敗でもサーバーmiddlewareがCookieを更新し得る。
    const result = await markUnknown(auth, intent, epoch)
    if (result.status === 'stale') await invalidateCookieUncertainty(auth)
    return result
  }
}

/** guardと画面の同時呼出しは同じPinia・世代の1要求に集約する。 */
export function ensureSessionVerified(): Promise<SessionResult> {
  const auth = store()
  if (pendingMutation(auth))
    return Promise.reject(new AuthOperationInProgressError())
  if (auth.automaticVerificationBlocked) return Promise.resolve(unknown(auth))
  if (auth.isAuthenticated && auth.teamId !== null)
    return Promise.resolve(authenticated(auth))
  const pending = sessions.get(auth)
  if (pending?.epoch === auth.authEpoch) return pending.promise
  const previous = lastChecks.get(auth)
  if (previous?.authEpoch === auth.authEpoch) return Promise.resolve(previous)
  return verify(false)
}

/** 明示再確認は期待IDが既知の時だけsession GETを送り、資格情報を再送しない。 */
export function session(
  options: { signal?: AbortSignal } = {},
): Promise<SessionResult> {
  return verify(true, options.signal)
}
function verify(
  explicit: boolean,
  signal?: AbortSignal,
): Promise<SessionResult> {
  const auth = store()
  if (pendingMutation(auth))
    return Promise.reject(new AuthOperationInProgressError())
  const pending = sessions.get(auth)
  if (pending?.epoch === auth.authEpoch) return pending.promise
  const entry: Pending<SessionResult> = {
    epoch: auth.authEpoch,
    promise: Promise.resolve(unknown(auth)),
  }
  entry.promise = (async () => {
    try {
      const start = await withAuthIntent((intent) => {
        auth.syncFromStorage()
        if (
          auth.explicitLoginRequired ||
          !intent?.tenantId ||
          (intent.phase !== 'expected' &&
            !(explicit && intent.phase === 'verification-required'))
        ) {
          if (!auth.explicitLoginRequired)
            auth.beginCorrelatedVerification(intent?.intentId ?? null)
          return null
        }
        const epoch = auth.beginCorrelatedVerification(intent.intentId)
        entry.epoch = epoch
        return { intent, epoch }
      })
      if (!start) return unknown(auth)
      entry.epoch = start.epoch
      return readSession(auth, start.intent, start.epoch, signal)
    } catch (error) {
      return failedEnvironment(auth, error)
    }
  })()
  sessions.set(auth, entry)
  void entry.promise.finally(() => {
    if (sessions.get(auth) === entry) sessions.delete(auth)
  })
  return entry.promise
}

/** 明示loginの送信前に破棄し、失敗・拒否後も旧cacheを復元しない。 */
export async function login(
  credentials: { team_name: string; password: string },
  options: { signal?: AbortSignal } = {},
): Promise<LoginResult> {
  const auth = store()
  if (pendingMutation(auth) || sessions.get(auth)?.epoch === auth.authEpoch)
    throw new AuthOperationInProgressError()
  const entry = { epoch: auth.authEpoch }
  mutations.set(auth, entry)
  let intent: AuthIntent | undefined
  let uncertaintyNotified = false
  const onUncertain = async () => {
    if (uncertaintyNotified) return
    uncertaintyNotified = true
    try {
      const changed = await withAuthIntent((now) => {
        auth.syncFromStorage()
        return (
          now?.intentId !== intent?.intentId || auth.authEpoch !== entry.epoch
        )
      })
      if (changed) await invalidateCookieUncertainty(auth)
    } catch (error) {
      failedEnvironment(auth, error)
    }
  }
  try {
    intent = await withAuthIntent(() => {
      // storage/lock不使用時にも旧メモリは残さない。
      const next = writeAuthIntent('pending', null)
      entry.epoch = auth.beginCorrelatedVerification(next.intentId)
      return next
    })
    const value = await apiRequest<unknown>('POST', '/auth/login', {
      body: credentials,
      signal: options.signal,
      noAuthExpiry: true,
      onAuthCookieUncertain: onUncertain,
    })
    const start = await withAuthIntent((now) => {
      auth.syncFromStorage()
      if (now?.intentId !== intent!.intentId || auth.authEpoch !== entry.epoch)
        return null
      if (
        !object(value) ||
        Object.keys(value).length !== 2 ||
        value.status !== 'authenticated' ||
        typeof value.tenant_id !== 'string' ||
        !canonicalUuid.test(value.tenant_id)
      )
        return undefined
      const next = writeAuthIntent('expected', value.tenant_id)
      entry.epoch = auth.beginCorrelatedVerification(next.intentId)
      return next
    })
    if (start === null) return { status: 'stale', authEpoch: entry.epoch }
    if (!start) return markUnknown(auth, intent, entry.epoch)
    return await readSession(auth, start, entry.epoch, options.signal)
  } catch (error) {
    if (error instanceof AuthEnvironmentError)
      return failedEnvironment(auth, error)
    auth.syncFromStorage()
    if (error instanceof ApiStaleAuthError || auth.authEpoch !== entry.epoch)
      return { status: 'stale', authEpoch: entry.epoch }
    if (!intent) return unknown(auth)
    const result = await markUnknown(auth, intent, entry.epoch)
    if (
      result.status !== 'stale' &&
      error instanceof ApiError &&
      (error.status === 401 || error.status === 429)
    )
      return {
        status: 'rejected',
        authEpoch: auth.authEpoch,
        httpStatus: error.status,
      }
    return result
  } finally {
    if (mutations.get(auth) === entry) mutations.delete(auth)
  }
}

export async function logout(
  options: { signal?: AbortSignal } = {},
): Promise<LogoutResult> {
  const auth = store()
  if (pendingMutation(auth)) throw new AuthOperationInProgressError()
  const entry = { epoch: auth.authEpoch }
  mutations.set(auth, entry)
  let intent: AuthIntent | undefined
  let notified = false
  try {
    intent = await withAuthIntent(() => {
      const next = writeAuthIntent('signed-out', null)
      entry.epoch = auth.beginCorrelatedVerification(next.intentId)
      return next
    })
    const value = await apiRequest<unknown>('POST', '/auth/logout', {
      signal: options.signal,
      noAuthExpiry: true,
      onAuthCookieUncertain: async () => {
        if (notified) return
        notified = true
        auth.syncFromStorage()
        const stale = await withAuthIntent(
          (now) =>
            now?.intentId !== intent!.intentId ||
            auth.authEpoch !== entry.epoch,
        )
        if (stale) await invalidateCookieUncertainty(auth)
      },
    })
    return await withAuthIntent((now) => {
      auth.syncFromStorage()
      if (now?.intentId !== intent!.intentId || auth.authEpoch !== entry.epoch)
        return { status: 'stale' as const, authEpoch: entry.epoch }
      if (
        !object(value) ||
        Object.keys(value).length !== 1 ||
        value.status !== 'logged_out'
      )
        return unknown(auth)
      return { status: 'logged-out' as const, authEpoch: auth.authEpoch }
    })
  } catch (error) {
    if (error instanceof AuthEnvironmentError)
      return failedEnvironment(auth, error)
    auth.syncFromStorage()
    if (error instanceof ApiStaleAuthError || auth.authEpoch !== entry.epoch)
      return { status: 'stale', authEpoch: entry.epoch }
    if (intent && error instanceof ApiError && error.status === 401)
      return { status: 'logged-out', authEpoch: auth.authEpoch }
    return unknown(auth)
  } finally {
    if (mutations.get(auth) === entry) mutations.delete(auth)
  }
}

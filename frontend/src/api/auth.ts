import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import {
  AuthEnvironmentError,
  canonicalUuid,
  captureAuthUncertainty,
  readAuthIntent,
  withAuthIntent,
  writeAuthIntent,
  type AuthIntent,
} from './authIntent'
import {
  ApiError,
  ApiNetworkError,
  ApiStaleAuthError,
  apiRequest,
} from './client'

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
  await auth.invalidateUncertainCookie()
  unknown(auth)
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
  notice: string | null,
  signal?: AbortSignal,
): Promise<SessionResult> {
  let responseParsed = false
  let uncertaintyHandled = false
  try {
    const value = await apiRequest<unknown>('GET', '/auth/session', {
      noAuthExpiry: true,
      signal,
    })
    responseParsed = true
    const result = await withAuthIntent((now) => {
      auth.syncFromStorage()
      if (now?.intentId !== intent.intentId || auth.authEpoch !== epoch) {
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
        return null
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
        notice,
      )
      return authenticated(auth)
    })
    if (result === null) {
      uncertaintyHandled = true
      await auth.invalidateUncertainCookie()
      return unknown(auth)
    }
    return result
  } catch (error) {
    if (error instanceof AuthEnvironmentError) {
      if (responseParsed && !uncertaintyHandled)
        await auth.invalidateUncertainCookie()
      return failedEnvironment(auth, error)
    }
    if (error instanceof ApiStaleAuthError)
      return { status: 'stale', authEpoch: epoch }
    if (
      error instanceof ApiNetworkError &&
      !auth.isAuthenticated &&
      auth.automaticVerificationBlocked
    )
      return unknown(auth)

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
    if (error instanceof ApiError && error.status !== 401) {
      await auth.invalidateUncertainCookie()
      return unknown(auth)
    }
    if (!auth.isAuthenticated && auth.automaticVerificationBlocked)
      return unknown(auth)
    return markUnknown(auth, intent, epoch)
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
          (!explicit && auth.automaticVerificationBlocked) ||
          !intent?.tenantId ||
          (intent.phase !== 'expected' &&
            !(explicit && intent.phase === 'verification-required'))
        ) {
          if (!auth.explicitLoginRequired)
            auth.beginCorrelatedVerification(intent?.intentId ?? null)
          return null
        }
        const notice = captureAuthUncertainty(explicit)
        auth.syncFromStorage()
        const epoch = auth.beginCorrelatedVerification(intent.intentId)
        entry.epoch = epoch
        return { intent, epoch, notice }
      })
      if (!start) return unknown(auth)
      entry.epoch = start.epoch
      return readSession(auth, start.intent, start.epoch, start.notice, signal)
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
  let notice: string | null = null
  let uncertaintyNotified = false
  let outcomeUnknown = false
  const onUncertain = async (resultUnknown = false) => {
    outcomeUnknown ||= resultUnknown
    if (uncertaintyNotified) return
    uncertaintyNotified = true
    try {
      auth.syncFromStorage()
      const now = readAuthIntent()
      const changed =
        now?.intentId !== intent?.intentId || auth.authEpoch !== entry.epoch
      if (resultUnknown || changed) await invalidateCookieUncertainty(auth)
    } catch (error) {
      failedEnvironment(auth, error)
    }
  }
  try {
    intent = await withAuthIntent(() => {
      notice = captureAuthUncertainty(true)
      auth.syncFromStorage()
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
    return await readSession(auth, start, entry.epoch, notice, options.signal)
  } catch (error) {
    if (error instanceof AuthEnvironmentError)
      return failedEnvironment(auth, error)
    auth.syncFromStorage()
    if (outcomeUnknown) return unknown(auth)
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
  let outcomeUnknown = false
  try {
    intent = await withAuthIntent(() => {
      const next = writeAuthIntent('signed-out', null)
      entry.epoch = auth.beginCorrelatedVerification(next.intentId)
      return next
    })
    const value = await apiRequest<unknown>('POST', '/auth/logout', {
      signal: options.signal,
      noAuthExpiry: true,
      onAuthCookieUncertain: async (resultUnknown = false) => {
        outcomeUnknown ||= resultUnknown
        if (notified) return
        notified = true
        auth.syncFromStorage()
        const now = readAuthIntent()
        const stale =
          now?.intentId !== intent!.intentId || auth.authEpoch !== entry.epoch
        if (resultUnknown || stale) await invalidateCookieUncertainty(auth)
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
    if (outcomeUnknown)
      return { status: 'verification-unknown', authEpoch: auth.authEpoch }
    if (error instanceof ApiStaleAuthError || auth.authEpoch !== entry.epoch)
      return { status: 'stale', authEpoch: entry.epoch }
    if (intent && error instanceof ApiError && error.status === 401)
      return { status: 'logged-out', authEpoch: auth.authEpoch }
    return unknown(auth)
  } finally {
    if (mutations.get(auth) === entry) mutations.delete(auth)
  }
}

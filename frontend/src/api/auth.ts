import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
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
const uuidPattern =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

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

function current(auth: AuthStore, epoch: number): boolean {
  auth.syncFromStorage()
  return auth.authEpoch === epoch
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function exactStatus(value: unknown, status: string): boolean {
  return (
    object(value) && Object.keys(value).length === 1 && value.status === status
  )
}

function authenticated(auth: AuthStore): SessionResult {
  return {
    status: 'authenticated',
    authEpoch: auth.authEpoch,
    tenantId: auth.teamId!,
    teamName: auth.teamName!,
  }
}

function remember(auth: AuthStore, result: SessionResult): SessionResult {
  if (result.status !== 'stale' && auth.authEpoch === result.authEpoch)
    lastChecks.set(auth, result)
  return result
}

function unconfirmed(
  auth: AuthStore,
  epoch: number,
): { status: 'verification-unknown'; authEpoch: number } {
  const result = { status: 'verification-unknown' as const, authEpoch: epoch }
  remember(auth, result)
  return result
}

async function readSession(
  auth: AuthStore,
  epoch: number,
  signal?: AbortSignal,
): Promise<SessionResult> {
  try {
    const value = await apiRequest<unknown>('GET', '/auth/session', {
      noAuthExpiry: true,
      signal,
    })
    if (!current(auth, epoch)) return { status: 'stale', authEpoch: epoch }
    if (
      !object(value) ||
      Object.keys(value).length !== 2 ||
      typeof value.tenant_id !== 'string' ||
      !uuidPattern.test(value.tenant_id) ||
      typeof value.team_name !== 'string' ||
      value.team_name.length === 0
    ) {
      return unconfirmed(auth, epoch)
    }
    auth.signIn({ teamId: value.tenant_id, teamName: value.team_name })
    return authenticated(auth)
  } catch (error) {
    if (!current(auth, epoch) || error instanceof ApiStaleAuthError)
      return { status: 'stale', authEpoch: epoch }
    if (error instanceof ApiError && error.status === 401) {
      auth.expireSession()
      return remember(auth, {
        status: 'server-unauthenticated',
        authEpoch: auth.authEpoch,
      })
    }
    return unconfirmed(auth, epoch)
  }
}

function pendingMutation(auth: AuthStore): boolean {
  return mutations.get(auth)?.epoch === auth.authEpoch
}

/** guardと画面の同時呼出しは同じPinia・世代の1要求に集約する。 */
export function ensureSessionVerified(): Promise<SessionResult> {
  const auth = store()
  if (pendingMutation(auth))
    return Promise.reject(new AuthOperationInProgressError())
  if (auth.isAuthenticated && auth.teamId !== null)
    return Promise.resolve(authenticated(auth))
  const pending = sessions.get(auth)
  if (pending?.epoch === auth.authEpoch) return pending.promise
  const previous = lastChecks.get(auth)
  if (previous?.authEpoch === auth.authEpoch) return Promise.resolve(previous)
  return session()
}

/** 明示再確認はsession GETだけを送り、資格情報を再送しない。 */
export function session(
  options: { signal?: AbortSignal } = {},
): Promise<SessionResult> {
  const auth = store()
  if (pendingMutation(auth))
    return Promise.reject(new AuthOperationInProgressError())
  const pending = sessions.get(auth)
  if (pending?.epoch === auth.authEpoch) return pending.promise
  const epoch = auth.beginSessionVerification()
  const entry: Pending<SessionResult> = {
    epoch,
    promise: readSession(auth, epoch, options.signal),
  }
  sessions.set(auth, entry)
  void entry.promise.finally(() => {
    if (sessions.get(auth) === entry) sessions.delete(auth)
  })
  return entry.promise
}

/** 失敗が確定しないPOSTを自動再送しない。 */
export async function login(
  credentials: { team_name: string; password: string },
  options: { signal?: AbortSignal } = {},
): Promise<LoginResult> {
  const auth = store()
  if (pendingMutation(auth)) throw new AuthOperationInProgressError()
  if (sessions.get(auth)?.epoch === auth.authEpoch)
    throw new AuthOperationInProgressError()
  const entry = { epoch: auth.authEpoch }
  mutations.set(auth, entry)
  let cookieChanged = false
  let staleCookie = false
  const discardPrevious = () => {
    staleCookie = !current(auth, entry.epoch)
    entry.epoch = auth.beginSessionVerification()
    cookieChanged = true
    // 旧要求から新tenant/成功を採らず、Cookieとの一致が不明という情報だけを残す。
    if (staleCookie) unconfirmed(auth, entry.epoch)
  }
  try {
    const value = await apiRequest<unknown>('POST', '/auth/login', {
      body: credentials,
      signal: options.signal,
      noAuthExpiry: true,
      onAuthCookieUncertain: discardPrevious,
    })
    if (!current(auth, entry.epoch))
      return { status: 'stale', authEpoch: entry.epoch }
    if (!exactStatus(value, 'authenticated'))
      return unconfirmed(auth, entry.epoch)
    return await readSession(auth, entry.epoch, options.signal)
  } catch (error) {
    if (staleCookie && current(auth, entry.epoch))
      return unconfirmed(auth, entry.epoch)
    if (!current(auth, entry.epoch) || error instanceof ApiStaleAuthError)
      return { status: 'stale', authEpoch: entry.epoch }
    if (
      !cookieChanged &&
      error instanceof ApiError &&
      (error.status < 200 || error.status >= 300)
    ) {
      return {
        status: 'rejected',
        httpStatus: error.status,
        authEpoch: entry.epoch,
      }
    }
    if (!cookieChanged) discardPrevious()
    return unconfirmed(auth, entry.epoch)
  } finally {
    if (mutations.get(auth) === entry) mutations.delete(auth)
  }
}

export async function logout(
  options: { signal?: AbortSignal } = {},
): Promise<LogoutResult> {
  const auth = store()
  if (pendingMutation(auth)) throw new AuthOperationInProgressError()
  const entry = { epoch: auth.beginSessionVerification() }
  mutations.set(auth, entry)
  let staleCookie = false
  try {
    const value = await apiRequest<unknown>('POST', '/auth/logout', {
      signal: options.signal,
      noAuthExpiry: true,
      onAuthCookieUncertain: () => {
        if (current(auth, entry.epoch)) return
        staleCookie = true
        entry.epoch = auth.beginSessionVerification()
        unconfirmed(auth, entry.epoch)
      },
    })
    if (!current(auth, entry.epoch))
      return { status: 'stale', authEpoch: entry.epoch }
    if (!exactStatus(value, 'logged_out')) return unconfirmed(auth, entry.epoch)
  } catch (error) {
    if (staleCookie && current(auth, entry.epoch))
      return unconfirmed(auth, entry.epoch)
    if (!current(auth, entry.epoch) || error instanceof ApiStaleAuthError)
      return { status: 'stale', authEpoch: entry.epoch }
    if (!(error instanceof ApiError && error.status === 401))
      return unconfirmed(auth, entry.epoch)
  } finally {
    if (mutations.get(auth) === entry) mutations.delete(auth)
  }
  auth.signOut()
  remember(auth, {
    status: 'server-unauthenticated',
    authEpoch: auth.authEpoch,
  })
  return { status: 'logged-out', authEpoch: auth.authEpoch }
}

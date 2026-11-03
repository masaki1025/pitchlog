import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import type { ApiErrorBody } from './types'

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export type SyncRequestCredentials = Readonly<{
  deviceId: string
  deviceCredential: string
  attempt: string
}>

export interface RequestOptions {
  /** 同期POST専用。資格を他経路へ転送しない。 */
  syncCredentials?: SyncRequestCredentials
  body?: unknown
  query?: Record<
    string,
    | string
    | number
    | boolean
    | null
    | undefined
    | readonly (string | number | boolean)[]
  >
  /** 承認済みroster 7経路だけでtenant照合証跡を要求する。 */
  tenantBound?: boolean
  noAuthExpiry?: boolean
  /** Cookie変更可能な成功headers/通信結果不明を、世代判定より先に一度だけ通知する。 */
  onAuthCookieUncertain?: (resultUnknown?: boolean) => void | Promise<void>
  signal?: AbortSignal
}

export class ApiError extends Error {
  status: number
  fields: { location: string }[]
  retryAfterMs: number | undefined
  body: unknown

  constructor(
    status: number,
    message: string,
    fields: { location: string }[],
    retryAfterMs: number | undefined,
    body: unknown,
    cause?: unknown,
  ) {
    super(message, cause === undefined ? undefined : { cause })
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
    this.retryAfterMs = retryAfterMs
    this.body = body
  }
}

export class ApiSessionUnverifiedError extends Error {
  constructor() {
    super('ログイン状態の確認が完了していません')
    this.name = 'ApiSessionUnverifiedError'
  }
}

export class ApiNetworkError extends Error {
  cause: unknown

  constructor(cause: unknown) {
    super('ネットワーク通信に失敗しました')
    this.name = 'ApiNetworkError'
    this.cause = cause
  }
}

export class ApiStaleAuthError extends Error {
  method: HttpMethod
  path: string
  status: number | undefined

  constructor(method: HttpMethod, path: string, status?: number) {
    super(
      '認証が切り替わったため応答を破棄しました。サーバーで処理された可能性があり、結果は未確認です',
    )
    this.name = 'ApiStaleAuthError'
    this.method = method
    this.path = path
    this.status = status
  }
}

/** tenant照合が成立せず、処理結果を採用できない。自動再送しない。 */
export class ApiTenantVerificationError extends ApiStaleAuthError {
  constructor(method: HttpMethod, path: string, status?: number) {
    super(method, path, status)
    this.name = 'ApiTenantVerificationError'
    this.message =
      'テナントの照合を確認できないため認証状態と操作結果は未確認です。自動再送せずログイン状態を再確認してください'
  }
}

function isCanonicalUuid(value: string | null): value is string {
  return (
    value !== null &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value)
  )
}

function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'AbortError'
  )
}

function queryString(query: RequestOptions['query']): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null) {
      continue
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, String(item))
      }
    } else {
      params.append(key, String(value))
    }
  }
  const encoded = params.toString()
  return encoded ? `?${encoded}` : ''
}

function parseRetryAfterMs(value: string | null): number | undefined {
  const trimmed = value?.trim()
  if (!trimmed) {
    return undefined
  }
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) {
    const seconds = Number(trimmed)
    return Number.isFinite(seconds)
      ? Math.max(0, Math.ceil(seconds * 1000))
      : undefined
  }
  const timestamp = Date.parse(trimmed)
  return Number.isFinite(timestamp)
    ? Math.max(0, timestamp - Date.now())
    : undefined
}

function isErrorEnvelope(body: unknown): body is ApiErrorBody {
  if (typeof body !== 'object' || body === null || !('error' in body)) {
    return false
  }
  const detail = body.error
  return (
    typeof detail === 'object' &&
    detail !== null &&
    'message' in detail &&
    typeof detail.message === 'string'
  )
}

function envelopeFields(body: ApiErrorBody): { location: string }[] {
  const fields = body.error.fields
  return Array.isArray(fields) &&
    fields.every((field) => typeof field?.location === 'string')
    ? fields
    : []
}

function parseResponseBody(
  res: Response,
  raw: string,
): {
  raw: string
  body: unknown
  isJson: boolean
  invalidJson: boolean
} {
  const isJson = (res.headers.get('content-type') ?? '')
    .toLowerCase()
    .includes('json')
  let body: unknown = raw
  let invalidJson = false
  if (raw && isJson) {
    try {
      body = JSON.parse(raw)
    } catch {
      invalidJson = true
    }
  }
  return { raw, body, isJson, invalidJson }
}

async function requestResponse<T>(
  method: HttpMethod,
  path: string,
  options: RequestOptions,
  readSuccess: (res: Response) => Promise<T>,
): Promise<{ res: Response; body: T }> {
  const pinia = getActivePinia()
  if (!pinia) {
    throw new Error('Pinia が未インストールのため API を呼べません')
  }

  const auth = useAuthStore(pinia)
  auth.syncFromStorage()
  if (
    (!auth.isAuthenticated || auth.teamId === null) &&
    !(
      (method === 'GET' && path === '/auth/session') ||
      (method === 'POST' && (path === '/auth/login' || path === '/auth/logout'))
    )
  ) {
    throw new ApiSessionUnverifiedError()
  }
  let epoch = auth.authEpoch
  const expectedTenant = auth.teamId
  if (options.tenantBound && !isCanonicalUuid(expectedTenant)) {
    throw new ApiTenantVerificationError(method, path)
  }
  const challenge = options.tenantBound ? crypto.randomUUID() : undefined
  const tenantChanged = () =>
    options.tenantBound &&
    (auth.authEpoch !== epoch ||
      auth.teamId !== expectedTenant ||
      !auth.isAuthenticated)

  // 現存するtenant認証付き経路はCookieを更新し得る。認可の判定には使わない。
  const cookieMayRenew =
    ['/auth/session', '/auth/password', '/auth/login', '/auth/logout'].includes(
      path,
    ) ||
    (method === 'POST' && path === '/devices/enroll') ||
    /^\/(?:players|team-records|games)(?:\/|$)/.test(path)
  if (
    options.onAuthCookieUncertain &&
    !(method === 'POST' && (path === '/auth/login' || path === '/auth/logout'))
  ) {
    throw new Error('認証Cookieフックはlogin/logoutだけで利用できます')
  }

  const sync = options.syncCredentials
  if (
    sync !== undefined &&
    (method !== 'POST' ||
      !/^\/games\/[0-9a-f-]{36}\/sync\/events$/.test(path) ||
      !isCanonicalUuid(sync.deviceId) ||
      !isCanonicalUuid(sync.attempt) ||
      !/^[\x21-\x7e]+$/.test(sync.deviceCredential))
  ) {
    throw new Error('同期要求の資格または送信先が不正です')
  }
  const headers: Record<string, string> = {}
  if (sync !== undefined) {
    headers['X-Pitchlog-Device-Id'] = sync.deviceId
    headers['X-Pitchlog-Device-Credential'] = sync.deviceCredential
    headers['X-Pitchlog-Sync-Attempt'] = sync.attempt
  }
  if (options.tenantBound) {
    headers['X-Pitchlog-Expected-Tenant'] = expectedTenant!
    headers['X-Pitchlog-Tenant-Challenge'] = challenge!
  }
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (method !== 'GET') {
    headers['X-Pitchlog-Request'] = '1'
  }

  const url = `/api${path}${queryString(options.query)}`
  const init: RequestInit = {
    method,
    credentials: 'include',
    ...(options.tenantBound ? { cache: 'no-store' as const } : {}),
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  }
  let res: Response
  try {
    res = await fetch(url, init)
  } catch (error) {
    // HTTP応答が得られなくてもCookie変更済みの可能性は残る。
    auth.syncFromStorage()
    // 結果不明なら現世代でもCookieが変わり得る。要求につき通知経路は一つ。
    if (options.onAuthCookieUncertain) await options.onAuthCookieUncertain(true)
    else if (cookieMayRenew) await auth.invalidateUncertainCookie()
    if (tenantChanged()) throw new ApiTenantVerificationError(method, path)
    if (isAbortError(error)) {
      throw error
    }
    throw new ApiNetworkError(error)
  }

  // Set-CookieはJSより先に適用される。古い応答でも無効化だけは先に通知する。
  auth.syncFromStorage()
  const stale = auth.authEpoch !== epoch
  // C2のtenant/nonce拒否より先に、古いheadersによるCookie不確実性を無効化する。
  if (
    stale &&
    cookieMayRenew &&
    res.status !== 401 &&
    !options.onAuthCookieUncertain
  )
    await auth.invalidateUncertainCookie()
  if (res.ok && options.onAuthCookieUncertain) {
    await options.onAuthCookieUncertain()
    if (!stale) epoch = auth.authEpoch
  }
  if (tenantChanged())
    throw new ApiTenantVerificationError(method, path, res.status)
  if (stale) throw new ApiStaleAuthError(method, path, res.status)
  if (
    options.tenantBound &&
    res.ok &&
    (res.headers.get('X-Pitchlog-Tenant-Match') !== '1' ||
      res.headers.get('X-Pitchlog-Tenant-Challenge') !== challenge)
  ) {
    // Set-Cookieは本文/metadata検査より先に適用され得る。成功や旧cacheを採らない。
    await auth.invalidateUncertainCookie()
    throw new ApiTenantVerificationError(method, path, res.status)
  }

  let readResult:
    | {
        ok: true
        value: { kind: 'success'; body: T } | { kind: 'error'; raw: string }
      }
    | { ok: false; cause: unknown }
  try {
    readResult = res.ok
      ? { ok: true, value: { kind: 'success', body: await readSuccess(res) } }
      : { ok: true, value: { kind: 'error', raw: await res.text() } }
  } catch (cause) {
    readResult = { ok: false, cause }
  }

  // 本文の読み取り中にも認証が切り替わり得るため、結果を解釈する前に再照合する。
  auth.syncFromStorage()
  if (tenantChanged())
    throw new ApiTenantVerificationError(method, path, res.status)
  if (auth.authEpoch !== epoch) {
    throw new ApiStaleAuthError(method, path, res.status)
  }

  if (res.status === 401 && !options.noAuthExpiry) {
    auth.expireSession()
  }

  if (!readResult.ok) {
    // session本文が読めなければCookieとの一致も未確認。業務のDTO不正とは区別する。
    if (res.ok && path === '/auth/session')
      await auth.invalidateUncertainCookie()
    const cause = readResult.cause
    if (isAbortError(cause)) {
      throw cause
    }
    if (!res.ok) {
      throw new ApiError(
        res.status,
        `HTTP ${res.status}`,
        [],
        parseRetryAfterMs(res.headers.get('retry-after')),
        undefined,
        cause,
      )
    }
    throw new ApiNetworkError(cause)
  }
  if (readResult.value.kind === 'success') {
    return { res, body: readResult.value.body }
  }

  const { body } = parseResponseBody(res, readResult.value.raw)
  const envelope = isErrorEnvelope(body) ? body : undefined
  throw new ApiError(
    res.status,
    envelope?.error.message ?? `HTTP ${res.status}`,
    envelope ? envelopeFields(envelope) : [],
    parseRetryAfterMs(res.headers.get('retry-after')),
    body,
  )
}

export async function apiRequest<T>(
  method: HttpMethod,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { res, body: raw } = await requestResponse(
    method,
    path,
    options,
    (res) => res.text(),
  )
  const { body, isJson, invalidJson } = parseResponseBody(res, raw)
  if (res.status === 204 || !raw) {
    return undefined as T
  }
  if (!isJson || invalidJson) {
    throw new ApiError(res.status, '応答を解釈できません', [], undefined, raw)
  }
  return body as T
}

function downloadFilename(header: string | null): string | null {
  if (!header) {
    return null
  }
  const encoded = /(?:^|;)\s*filename\*\s*=\s*([^;]*)/i.exec(header)
  if (encoded) {
    const value = /^UTF-8''(.+)$/i.exec(encoded[1]?.trim() ?? '')
    if (!value) {
      return null
    }
    try {
      return decodeURIComponent(value[1]!)
    } catch {
      return null
    }
  }
  const plain = /(?:^|;)\s*filename\s*=\s*(?:"([^"]*)"|([^;]*))/i.exec(header)
  const filename = plain?.[1] ?? plain?.[2]?.trim()
  return filename || null
}

export async function apiDownload(
  path: string,
  options: {
    query?: RequestOptions['query']
    signal?: AbortSignal
    noAuthExpiry?: boolean
  } = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const { res, body: blob } = await requestResponse(
    'GET',
    path,
    options,
    (res) => res.blob(),
  )
  return {
    blob,
    filename: downloadFilename(res.headers.get('content-disposition')),
  }
}

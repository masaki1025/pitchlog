import { getActivePinia } from 'pinia'
import { useAuthStore } from '../stores/authStore'
import type { ApiErrorBody } from './types'

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'

export interface RequestOptions {
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
  noAuthExpiry?: boolean
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
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields
    this.retryAfterMs = retryAfterMs
    this.body = body
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

async function readResponseBody(res: Response): Promise<{
  raw: string
  body: unknown
  isJson: boolean
  invalidJson: boolean
}> {
  const raw = await res.text()
  const isJson = (res.headers.get('content-type') ?? '')
    .toLowerCase()
    .includes('json')
  let body: unknown = raw || undefined
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

async function requestResponse(
  method: HttpMethod,
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const pinia = getActivePinia()
  if (!pinia) {
    throw new Error('Pinia が未インストールのため API を呼べません')
  }

  const auth = useAuthStore(pinia)
  auth.syncFromStorage()
  const epoch = auth.authEpoch

  const headers: Record<string, string> = {}
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
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  }
  let res: Response
  try {
    res = await fetch(url, init)
  } catch (error) {
    if (
      typeof error === 'object' &&
      error !== null &&
      'name' in error &&
      error.name === 'AbortError'
    ) {
      throw error
    }
    throw new ApiNetworkError(error)
  }

  // 古い認証の応答は、本文や状態コードを処理する前に破棄する。
  auth.syncFromStorage()
  if (auth.authEpoch !== epoch) {
    throw new ApiStaleAuthError(method, path, res.status)
  }

  if (res.ok) {
    return res
  }

  const { body } = await readResponseBody(res)
  if (res.status === 401 && !options.noAuthExpiry) {
    auth.expireSession()
  }
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
  const res = await requestResponse(method, path, options)
  const { raw, body, isJson, invalidJson } = await readResponseBody(res)
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
  const res = await requestResponse('GET', path, options)
  const blob = await res.blob()
  return {
    blob,
    filename: downloadFilename(res.headers.get('content-disposition')),
  }
}

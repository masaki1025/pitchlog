import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from '../stores/authStore'
import {
  ApiError,
  ApiNetworkError,
  ApiStaleAuthError,
  apiDownload,
  apiRequest,
  type HttpMethod,
} from './client'

let pinia: Pinia

function respond(
  body: string | null,
  status = 200,
  headers: HeadersInit = { 'Content-Type': 'application/json' },
): void {
  vi.mocked(fetch).mockResolvedValue(new Response(body, { status, headers }))
}

function writeOtherTabAuth(): string {
  const raw = JSON.stringify({
    version: 1,
    sessionId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    teamName: 'B',
    teamId: null,
  })
  localStorage.setItem(AUTH_STORAGE_KEY, raw)
  return raw
}

function deferredValue<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
} {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function deferredResponse(): ReturnType<typeof deferredValue<Response>> {
  return deferredValue<Response>()
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  disposePinia(pinia)
  queryClient.clear()
})

describe('apiRequest', () => {
  it('送り先に /api と query を付け、null と undefined を省き、配列を繰り返す', async () => {
    respond('{}')

    await apiRequest('GET', '/players', {
      query: {
        limit: 20,
        cursor: null,
        omitted: undefined,
        active: false,
        tags: ['a', 'b'],
      },
    })

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/players?limit=20&active=false&tags=a&tags=b',
      expect.any(Object),
    )
  })

  it('Cookie を送るため credentials: include を指定する', async () => {
    respond('{}')

    await apiRequest('GET', '/players')

    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      credentials: 'include',
    })
  })

  it.each<HttpMethod>(['POST', 'PATCH', 'PUT', 'DELETE'])(
    '%s に X-Pitchlog-Request を付け、Authorization は付けない',
    async (method) => {
      respond('{}')

      await apiRequest(method, '/players')

      expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).toEqual({
        'X-Pitchlog-Request': '1',
      })
    },
  )

  it('GET に X-Pitchlog-Request と Authorization を付けない', async () => {
    respond('{}')

    await apiRequest('GET', '/players')

    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).toEqual({})
  })

  it('本文を JSON 化して Content-Type を付け、signal を渡す', async () => {
    respond('{}')
    const controller = new AbortController()

    await apiRequest('POST', '/players', {
      body: { name: '山田' },
      signal: controller.signal,
    })

    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      body: '{"name":"山田"}',
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Pitchlog-Request': '1',
      },
    })
  })

  it('本文が無いとき Content-Type を付けない', async () => {
    respond('{}')

    await apiRequest('POST', '/players')

    expect(vi.mocked(fetch).mock.calls[0]?.[1]).toMatchObject({
      body: undefined,
      headers: { 'X-Pitchlog-Request': '1' },
    })
  })

  it('JSON の成功応答を返す', async () => {
    respond('{"id":"p1"}', 200, { 'Content-Type': 'application/json' })

    await expect(
      apiRequest<{ id: string }>('GET', '/players/p1'),
    ).resolves.toStrictEqual({ id: 'p1' })
  })

  it('204 の応答は undefined を返す', async () => {
    respond(null, 204)

    await expect(apiRequest('DELETE', '/players/p1')).resolves.toBeUndefined()
  })

  it('空本文の応答は undefined を返す', async () => {
    respond('', 200, { 'Content-Type': 'application/json' })

    await expect(apiRequest('GET', '/players')).resolves.toBeUndefined()
  })

  it('エラー封筒の message と 422 の fields を写す', async () => {
    const body = {
      error: {
        message: '入力を確認してください',
        fields: [{ location: 'body.name' }],
      },
    }
    respond(JSON.stringify(body), 422, { 'Content-Type': 'application/json' })

    const error = await apiRequest('POST', '/players').catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      name: 'ApiError',
      status: 422,
      message: '入力を確認してください',
      fields: [{ location: 'body.name' }],
      body,
    })
  })

  it('fields が無い封筒では空配列にする', async () => {
    respond('{"error":{"message":"失敗"}}', 400, {
      'Content-Type': 'application/json',
    })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      message: '失敗',
      fields: [],
    })
  })

  it('封筒でない 409 の JSON 本文を保ち、HTTP 409 を一度だけ投げる', async () => {
    const body = { boundary_result: 'x', current_version: 3 }
    respond(JSON.stringify(body), 409, { 'Content-Type': 'application/json' })

    const error = await apiRequest('POST', '/games/g1/sync/events').catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 409,
      message: 'HTTP 409',
      fields: [],
    })
    expect((error as ApiError).body).toStrictEqual(body)
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
  })

  it('text のエラー本文を文字列のまま保つ', async () => {
    respond('gateway failure', 502, { 'Content-Type': 'text/plain' })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      status: 502,
      message: 'HTTP 502',
      body: 'gateway failure',
    })
  })

  it('Retry-After の秒数をミリ秒へ変換する', async () => {
    respond('', 429, { 'Retry-After': '2.5' })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      retryAfterMs: 2500,
    })
  })

  it('Retry-After の HTTP-date を現在時刻との差に変換し、過去の日付は 0 にする', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-11T00:00:00.000Z'))
    respond('', 429, { 'Retry-After': 'Sun, 11 Oct 2026 00:00:03 GMT' })
    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      retryAfterMs: 3000,
    })

    respond('', 429, { 'Retry-After': 'Sat, 10 Oct 2026 00:00:00 GMT' })
    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      retryAfterMs: 0,
    })
  })

  it('不正な Retry-After は undefined にする', async () => {
    respond('', 429, { 'Retry-After': 'invalid' })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      retryAfterMs: undefined,
    })
  })

  it('送信前・fetch 後・本文後に syncFromStorage を呼ぶ', async () => {
    const auth = useAuthStore(pinia)
    const sync = vi.spyOn(auth, 'syncFromStorage')
    const response = new Response('{}', {
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text')
    vi.mocked(fetch).mockResolvedValue(response)

    await apiRequest('GET', '/players')

    expect(sync).toHaveBeenCalledTimes(3)
    expect(sync.mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(fetch).mock.invocationCallOrder[0]!,
    )
    expect(sync.mock.invocationCallOrder[1]).toBeGreaterThan(
      vi.mocked(fetch).mock.invocationCallOrder[0]!,
    )
    expect(sync.mock.invocationCallOrder[1]).toBeLessThan(
      readBody.mock.invocationCallOrder[0]!,
    )
    expect(sync.mock.invocationCallOrder[2]).toBeGreaterThan(
      readBody.mock.invocationCallOrder[0]!,
    )
  })

  it('401 で expireSession を呼び、sessionExpired を true にする', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    respond('{"error":{"message":"認証期限切れ"}}', 401, {
      'Content-Type': 'application/json',
    })

    await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(ApiError)

    expect(expire).toHaveBeenCalledOnce()
    expect(auth.sessionExpired).toBe(true)
  })

  it('noAuthExpiry の 401 では expireSession を呼ばない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    respond('', 401)

    await expect(
      apiRequest('POST', '/login', { noAuthExpiry: true }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(expire).not.toHaveBeenCalled()
    expect(auth.sessionExpired).toBe(false)
    expect(auth.isAuthenticated).toBe(true)
  })

  it.each([403, 404, 409])(
    '%i は空本文を保つ ApiError にし、再試行しない',
    async (status) => {
      respond('', status)

      await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
        name: 'ApiError',
        status,
        message: `HTTP ${status}`,
        body: '',
      })
      expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1)
    },
  )

  it('fetch の reject は原因付き ApiNetworkError にする', async () => {
    const cause = new TypeError('offline')
    vi.mocked(fetch).mockRejectedValue(cause)

    const error = await apiRequest('GET', '/players').catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(ApiNetworkError)
    expect(error).toMatchObject({ name: 'ApiNetworkError', cause })
  })

  it('AbortError は同じ例外を投げ直す', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    vi.mocked(fetch).mockRejectedValue(abort)

    await expect(apiRequest('GET', '/players')).rejects.toBe(abort)
  })

  it('2xx の壊れた JSON は文字列を持つ ApiError にする', async () => {
    respond('{broken', 200, { 'Content-Type': 'application/json' })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      name: 'ApiError',
      status: 200,
      message: '応答を解釈できません',
      body: '{broken',
    })
  })

  it('2xx の JSON でない本文は ApiError にする', async () => {
    respond('ok', 200, { 'Content-Type': 'text/plain' })

    await expect(apiRequest('GET', '/players')).rejects.toMatchObject({
      name: 'ApiError',
      status: 200,
      message: '応答を解釈できません',
      body: 'ok',
    })
  })

  it('active Pinia が無ければ fetch の前に例外になる', async () => {
    setActivePinia(undefined)

    await expect(apiRequest('GET', '/players')).rejects.toThrow(
      'Pinia が未インストールのため API を呼べません',
    )
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('往復中に認証世代が変わると 200 の本文を読まず ApiStaleAuthError にする', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const request = apiRequest('GET', '/players')
    writeOtherTabAuth()
    const response = new Response('{"items":["A"]}', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text')
    pending.resolve(response)

    const error = await request.catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiStaleAuthError)
    expect(error).toMatchObject({
      method: 'GET',
      path: '/players',
      status: 200,
      message:
        '認証が切り替わったため応答を破棄しました。サーバーで処理された可能性があり、結果は未確認です',
    })
    expect(readBody).not.toHaveBeenCalled()
  })

  it('往復中に認証世代が変わると 401 でも新しい認証を失効させない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const request = apiRequest('POST', '/players', { body: { name: 'A' } })
    const savedB = writeOtherTabAuth()
    const response = new Response('{"error":{"message":"old session"}}', {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text')
    pending.resolve(response)

    await expect(request).rejects.toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'POST',
      path: '/players',
      status: 401,
    })
    expect(expire).not.toHaveBeenCalled()
    expect(readBody).not.toHaveBeenCalled()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(auth.teamName).toBe('B')
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.sessionExpired).toBe(false)
  })

  it('200 の本文を読む途中で認証が変わると値を返さない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const reading = deferredValue<void>()
    const body = deferredValue<string>()
    const response = new Response(null, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text').mockImplementation(() => {
      reading.resolve(undefined)
      return body.promise
    })
    vi.mocked(fetch).mockResolvedValue(response)

    const request = apiRequest('GET', '/players')
    await reading.promise
    const savedB = writeOtherTabAuth()
    body.resolve('{"items":["A"]}')

    const error = await request.catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiStaleAuthError)
    expect(error).toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/players',
      status: 200,
    })
    expect(readBody).toHaveBeenCalledOnce()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(auth.teamName).toBe('B')
  })

  it('401 の本文を読む途中で認証が変わると B を失効させない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    const reading = deferredValue<void>()
    const body = deferredValue<string>()
    const response = new Response(null, {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text').mockImplementation(() => {
      reading.resolve(undefined)
      return body.promise
    })
    vi.mocked(fetch).mockResolvedValue(response)

    const request = apiRequest('GET', '/players')
    await reading.promise
    const savedB = writeOtherTabAuth()
    body.resolve('{"error":{"message":"古い認証"}}')

    const error = await request.catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiStaleAuthError)
    expect(error).toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/players',
      status: 401,
    })
    expect(readBody).toHaveBeenCalledOnce()
    expect(expire).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.teamName).toBe('B')
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
  })

  it('401 の本文読み取り失敗でも失効して原因付き ApiNetworkError にする', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    const cause = new TypeError('read failed')
    const response = new Response(null, { status: 401 })
    vi.spyOn(response, 'text').mockRejectedValue(cause)
    vi.mocked(fetch).mockResolvedValue(response)

    const error = await apiRequest('GET', '/players').catch(
      (caught: unknown) => caught,
    )
    expect(error).toBeInstanceOf(ApiNetworkError)
    expect(error).toMatchObject({ cause })
    expect(expire).toHaveBeenCalledOnce()
    expect(auth.sessionExpired).toBe(true)
  })

  it('noAuthExpiry の 401 で本文読み取りが失敗しても失効しない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    const cause = new TypeError('read failed')
    const response = new Response(null, { status: 401 })
    vi.spyOn(response, 'text').mockRejectedValue(cause)
    vi.mocked(fetch).mockResolvedValue(response)

    const error = await apiRequest('GET', '/players', {
      noAuthExpiry: true,
    }).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiNetworkError)
    expect(error).toMatchObject({ cause })
    expect(expire).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.sessionExpired).toBe(false)
  })
})

describe('apiDownload', () => {
  it('Blob を返し、filename* の UTF-8 名を filename より優先する', async () => {
    respond('csv-data', 200, {
      'Content-Type': 'text/csv',
      'Content-Disposition':
        'attachment; filename="fallback.csv"; filename*=UTF-8\'\'%E6%8E%88%E7%90%83.csv',
    })

    const result = await apiDownload('/reports/game.csv')

    expect(result.blob).toBeInstanceOf(Blob)
    expect(await result.blob.text()).toBe('csv-data')
    expect(result.filename).toBe('授球.csv')
  })

  it('filename の引用符付き名を返す', async () => {
    respond('data', 200, {
      'Content-Disposition': 'attachment; filename="report.csv"',
    })

    const result = await apiDownload('/reports/game.csv')

    expect(result.filename).toBe('report.csv')
  })

  it('filename の引用符なし名を返す', async () => {
    respond('data', 200, {
      'Content-Disposition': 'attachment; filename=report.csv',
    })

    const result = await apiDownload('/reports/game.csv')

    expect(result.filename).toBe('report.csv')
  })

  it('Content-Disposition が無ければ filename は null にする', async () => {
    respond('data', 200, { 'Content-Type': 'text/csv' })

    const result = await apiDownload('/reports/game.csv')

    expect(result.filename).toBeNull()
  })

  it('filename* を解釈できなければ filename は null にする', async () => {
    respond('data', 200, {
      'Content-Disposition':
        'attachment; filename="fallback.csv"; filename*=UTF-8\'\'%E0%A4%A',
    })

    const result = await apiDownload('/reports/game.csv')

    expect(result.filename).toBeNull()
  })

  it('GET で /api の送り先と query、Cookie、signal を使い、追加ヘッダを付けない', async () => {
    respond('data')
    const controller = new AbortController()

    await apiDownload('/reports/game.csv', {
      query: { ids: [1, 2], skip: null },
      signal: controller.signal,
    })

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/reports/game.csv?ids=1&ids=2',
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
        headers: {},
        body: undefined,
        signal: controller.signal,
      }),
    )
  })

  it('401 で expireSession を呼ぶ', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    respond('{"error":{"message":"期限切れ"}}', 401)

    await expect(apiDownload('/reports/game.csv')).rejects.toBeInstanceOf(
      ApiError,
    )

    expect(expire).toHaveBeenCalledOnce()
    expect(auth.sessionExpired).toBe(true)
  })

  it('noAuthExpiry の 401 では expireSession を呼ばない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    respond('{"error":{"message":"認証失敗"}}', 401)

    await expect(
      apiDownload('/reports/game.csv', { noAuthExpiry: true }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(expire).not.toHaveBeenCalled()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.sessionExpired).toBe(false)
  })

  it('エラー封筒を ApiError に写し、本文と Retry-After を保つ', async () => {
    const body = {
      error: {
        message: '再試行してください',
        fields: [{ location: 'query.limit' }],
      },
    }
    respond(JSON.stringify(body), 429, {
      'Content-Type': 'application/json',
      'Retry-After': '3',
    })

    await expect(apiDownload('/reports/game.csv')).rejects.toMatchObject({
      name: 'ApiError',
      status: 429,
      message: '再試行してください',
      fields: [{ location: 'query.limit' }],
      retryAfterMs: 3000,
      body,
    })
  })

  it('fetch の reject は原因付き ApiNetworkError にする', async () => {
    const cause = new TypeError('offline')
    vi.mocked(fetch).mockRejectedValue(cause)

    await expect(apiDownload('/reports/game.csv')).rejects.toMatchObject({
      name: 'ApiNetworkError',
      cause,
    })
  })

  it('AbortError はそのまま投げ直す', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    vi.mocked(fetch).mockRejectedValue(abort)

    await expect(apiDownload('/reports/game.csv')).rejects.toBe(abort)
  })

  it('active Pinia が無ければ fetch せずに例外になる', async () => {
    setActivePinia(undefined)

    await expect(apiDownload('/reports/game.csv')).rejects.toThrow(
      'Pinia が未インストールのため API を呼べません',
    )
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('往復中に認証世代が変わると Blob を読まず ApiStaleAuthError にする', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const request = apiDownload('/reports/game.csv')
    writeOtherTabAuth()
    const response = new Response('old data', { status: 200 })
    const readBlob = vi.spyOn(response, 'blob')
    pending.resolve(response)

    const error = await request.catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiStaleAuthError)
    expect(error).toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/reports/game.csv',
      status: 200,
    })
    expect(readBlob).not.toHaveBeenCalled()
  })

  it('往復中に世代が変わった 401 は新しい認証を失効させない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const expire = vi.spyOn(auth, 'expireSession')
    const pending = deferredResponse()
    vi.mocked(fetch).mockReturnValue(pending.promise)
    const request = apiDownload('/reports/game.csv')
    const savedB = writeOtherTabAuth()
    const response = new Response('{"error":{"message":"old session"}}', {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })
    const readBody = vi.spyOn(response, 'text')
    pending.resolve(response)

    await expect(request).rejects.toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/reports/game.csv',
      status: 401,
    })
    expect(readBody).not.toHaveBeenCalled()
    expect(expire).not.toHaveBeenCalled()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(auth.teamName).toBe('B')
    expect(auth.isAuthenticated).toBe(true)
  })

  it('Blob を読む途中で認証が変わるとファイルを返さない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamName: 'A' })
    const reading = deferredValue<void>()
    const body = deferredValue<Blob>()
    const response = new Response(null, { status: 200 })
    const readBlob = vi.spyOn(response, 'blob').mockImplementation(() => {
      reading.resolve(undefined)
      return body.promise
    })
    vi.mocked(fetch).mockResolvedValue(response)

    const request = apiDownload('/reports/game.csv')
    await reading.promise
    const savedB = writeOtherTabAuth()
    body.resolve(new Blob(['A のファイル']))

    const error = await request.catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiStaleAuthError)
    expect(error).toMatchObject({
      name: 'ApiStaleAuthError',
      method: 'GET',
      path: '/reports/game.csv',
      status: 200,
    })
    expect(readBlob).toHaveBeenCalledOnce()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBe(savedB)
    expect(auth.teamName).toBe('B')
  })
})

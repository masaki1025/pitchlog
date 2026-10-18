import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from '../stores/authStore'
import {
  AuthOperationInProgressError,
  ensureSessionVerified,
  login,
  logout,
  session,
} from './auth'
import { ApiSessionUnverifiedError, apiRequest } from './client'

const a = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  b = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const credentials = { team_name: '入力値', password: 'test-only' }
let pinia: Pinia
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function respond(value: unknown, status = 200) {
  vi.mocked(fetch).mockResolvedValueOnce(response(value, status))
}
function deferred<T>() {
  let resolve!: (v: T) => void, reject!: (e: unknown) => void
  const promise = new Promise<T>((r, j) => {
    resolve = r
    reject = j
  })
  return { promise, resolve, reject }
}
function oldAuth() {
  const auth = useAuthStore()
  auth.signIn({ teamName: '旧A', teamId: a })
  queryClient.setQueryData(['old'], 'A秘密')
  return auth
}
function empty() {
  const auth = useAuthStore()
  expect(auth.isAuthenticated).toBe(false)
  expect(auth.teamId).toBeNull()
  expect(auth.teamName).toBeNull()
  expect(queryClient.getQueryCache().getAll()).toEqual([])
}
beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  disposePinia(pinia)
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('C1正規認証操作', () => {
  it('保存Aは認証せずCookie Bのsessionだけを採る', async () => {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        sessionId: a,
        teamName: '保存A',
        teamId: a,
      }),
    )
    const auth = useAuthStore()
    empty()
    await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(
      ApiSessionUnverifiedError,
    )
    expect(fetch).not.toHaveBeenCalled()
    respond({ tenant_id: b, team_name: '正規B' })
    expect(await ensureSessionVerified()).toMatchObject({
      status: 'authenticated',
      tenantId: b,
      teamName: '正規B',
      authEpoch: auth.authEpoch,
    })
    expect(auth.teamId).toBe(b)
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.credentials).toBe('include')
  })
  it('同時確認は1要求に集約し検証済みなら再送しない', async () => {
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const one = ensureSessionVerified(),
      two = ensureSessionVerified()
    expect(one).toBe(two)
    p.resolve(response({ tenant_id: b, team_name: 'B' }))
    await one
    await ensureSessionVerified()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it.each([401, 429, 422, 500])(
    'login %s拒否で既存認証/cacheを維持',
    async (status) => {
      const auth = oldAuth(),
        epoch = auth.authEpoch
      respond({ error: { message: '拒否' } }, status)
      expect(await login(credentials)).toMatchObject({
        status: 'rejected',
        httpStatus: status,
        authEpoch: epoch,
      })
      expect(auth.authEpoch).toBe(epoch)
      expect(auth.teamId).toBe(a)
      expect(queryClient.getQueryData(['old'])).toBe('A秘密')
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it('login成功headersで旧データを消し本文とsessionを待つ', async () => {
    const auth = oldAuth(),
      body = deferred<string>(),
      check = deferred<Response>()
    vi.mocked(fetch)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: () => body.promise,
      } as Response)
      .mockReturnValueOnce(check.promise)
    const work = login(credentials)
    await vi.waitFor(() => expect(auth.isAuthenticated).toBe(false))
    empty()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(
      ApiSessionUnverifiedError,
    )
    body.resolve(JSON.stringify({ status: 'authenticated' }))
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    empty()
    check.resolve(response({ tenant_id: b, team_name: '正規B' }))
    expect(await work).toMatchObject({
      status: 'authenticated',
      tenantId: b,
      teamName: '正規B',
    })
  })
  it.each([500, 404, 422])('session %sは結果未確認', async (status) => {
    oldAuth()
    respond({ status: 'authenticated' })
    respond({}, status)
    expect(await login(credentials)).toMatchObject({
      status: 'verification-unknown',
    })
    empty()
    expect(useAuthStore().sessionExpired).toBe(false)
  })
  it('session 401だけをサーバー未認証にする', async () => {
    oldAuth()
    respond({}, 401)
    expect(await session()).toMatchObject({ status: 'server-unauthenticated' })
    empty()
    expect(useAuthStore().sessionExpired).toBe(true)
  })
  it.each([
    {},
    null,
    [],
    { tenant_id: b },
    { tenant_id: 2, team_name: 'B' },
    { tenant_id: 'bad', team_name: 'B' },
    { tenant_id: b, team_name: '' },
    { tenant_id: b, team_name: 1 },
    { tenant_id: b, team_name: 'B', token: 'forbidden' },
  ])('不正2xx DTO %jを採らない', async (value) => {
    oldAuth()
    respond(value)
    expect(await session()).toMatchObject({ status: 'verification-unknown' })
    empty()
    expect(useAuthStore().sessionExpired).toBe(false)
  })
  it.each([new TypeError('offline'), new DOMException('cancel', 'AbortError')])(
    'login通信結果未確認では破棄し自動再送しない',
    async (error) => {
      oldAuth()
      vi.mocked(fetch).mockRejectedValueOnce(error)
      expect(await login(credentials)).toMatchObject({
        status: 'verification-unknown',
      })
      empty()
      expect(fetch).toHaveBeenCalledTimes(1)
      respond({ tenant_id: b, team_name: 'B' })
      await session()
      expect(vi.mocked(fetch).mock.calls.map((c) => c[1]?.method)).toEqual([
        'POST',
        'GET',
      ])
    },
  )
  it('login成功の不正DTOでも旧認証を復活しない', async () => {
    oldAuth()
    respond({ status: 'bad' })
    expect(await login(credentials)).toMatchObject({
      status: 'verification-unknown',
    })
    empty()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('不正JSONはsession未確認', async () => {
    oldAuth()
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{', { headers: { 'Content-Type': 'application/json' } }),
    )
    expect(await session()).toMatchObject({ status: 'verification-unknown' })
    empty()
  })
  it('遅延sessionは新tenant/cacheに触れない', async () => {
    const auth = oldAuth(),
      p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const work = session()
    auth.signIn({ teamName: '新B', teamId: b })
    queryClient.setQueryData(['new'], 'B秘密')
    const epoch = auth.authEpoch
    p.resolve(response({ tenant_id: a, team_name: '古A' }))
    expect(await work).toMatchObject({
      status: 'stale',
      authEpoch: epoch - 1,
    })
    expect(auth.teamId).toBe(b)
    expect(auth.authEpoch).toBe(epoch)
    expect(queryClient.getQueryData(['new'])).toBe('B秘密')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('遅延login通信結果不明は新tenantも安全側へ無効化する', async () => {
    const auth = oldAuth(),
      p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const work = login(credentials)
    auth.signIn({ teamName: 'B', teamId: b })
    const epoch = auth.authEpoch
    p.reject(new Error('offline'))
    expect(await work).toEqual({
      status: 'verification-unknown',
      authEpoch: epoch + 1,
    })
    empty()
    expect(auth.authEpoch).toBe(epoch + 1)
  })
  it('二重loginとlogin中sessionを開始しない', async () => {
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const work = login(credentials)
    await expect(login(credentials)).rejects.toBeInstanceOf(
      AuthOperationInProgressError,
    )
    await expect(ensureSessionVerified()).rejects.toBeInstanceOf(
      AuthOperationInProgressError,
    )
    expect(fetch).toHaveBeenCalledTimes(1)
    p.resolve(response({}, 401))
    await work
  })
  it('進行中sessionとloginの競合を拒否', async () => {
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const work = session()
    await expect(login(credentials)).rejects.toBeInstanceOf(
      AuthOperationInProgressError,
    )
    p.resolve(response({ tenant_id: b, team_name: 'B' }))
    await work
  })
  it.each([200, 401])('logout %sの確定結果だけ完了にする', async (status) => {
    oldAuth()
    respond(status === 200 ? { status: 'logged_out' } : {}, status)
    expect(await logout()).toMatchObject({ status: 'logged-out' })
    empty()
    expect(useAuthStore().sessionExpired).toBe(false)
  })
  it.each([500, 200])('logout不正(%s)は未確認', async (status) => {
    oldAuth()
    respond({}, status)
    expect(await logout()).toMatchObject({ status: 'verification-unknown' })
    empty()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('logout通信失敗後の明示確認はGETだけ', async () => {
    oldAuth()
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    expect(await logout()).toMatchObject({ status: 'verification-unknown' })
    empty()
    respond({ tenant_id: b, team_name: 'B' })
    await session()
    expect(vi.mocked(fetch).mock.calls.map((c) => c[1]?.method)).toEqual([
      'POST',
      'GET',
    ])
  })
  it('結果未確認後のensureは自動再送せず、明示sessionだけ再確認する', async () => {
    respond({}, 503)
    expect(await ensureSessionVerified()).toMatchObject({
      status: 'verification-unknown',
    })
    expect(await ensureSessionVerified()).toMatchObject({
      status: 'verification-unknown',
    })
    expect(fetch).toHaveBeenCalledTimes(1)
    respond({ tenant_id: b, team_name: 'B' })
    expect(await session()).toMatchObject({ status: 'authenticated' })
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('login未確認後のensureも自動再確認しない', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    await login(credentials)
    expect(await ensureSessionVerified()).toMatchObject({
      status: 'verification-unknown',
    })
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('成功headers後に遅延する本文は新tenantを変更しない', async () => {
    const auth = oldAuth(),
      body = deferred<string>()
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: () => body.promise,
    } as Response)
    const work = login(credentials)
    await vi.waitFor(() => expect(auth.isAuthenticated).toBe(false))
    auth.signIn({ teamName: 'B', teamId: b })
    queryClient.setQueryData(['new'], 'B秘密')
    const epoch = auth.authEpoch
    body.resolve(JSON.stringify({ status: 'authenticated' }))
    expect(await work).toMatchObject({ status: 'stale' })
    expect(auth.authEpoch).toBe(epoch)
    expect(auth.teamId).toBe(b)
    expect(queryClient.getQueryData(['new'])).toBe('B秘密')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it.each(['session', 'logout'] as const)(
    '%sの確定未認証をensureで自動再確認しない',
    async (kind) => {
      oldAuth()
      respond(
        kind === 'session' ? {} : { status: 'logged_out' },
        kind === 'session' ? 401 : 200,
      )
      const result = await (kind === 'session' ? session() : logout())
      expect(result.authEpoch).toBe(useAuthStore().authEpoch)
      expect(await ensureSessionVerified()).toEqual({
        status: 'server-unauthenticated',
        authEpoch: useAuthStore().authEpoch,
      })
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it('login成功後のsession待ちにも認証操作の競合を拒否する', async () => {
    oldAuth()
    const check = deferred<Response>()
    respond({ status: 'authenticated' })
    vi.mocked(fetch).mockReturnValueOnce(check.promise)
    const work = login(credentials)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    await expect(session()).rejects.toBeInstanceOf(AuthOperationInProgressError)
    await expect(logout()).rejects.toBeInstanceOf(AuthOperationInProgressError)
    check.resolve(response({ tenant_id: b, team_name: 'B' }))
    const result = await work
    expect(result.authEpoch).toBe(useAuthStore().authEpoch)
  })
  it('login成功の壊れたJSONも旧認証を戻さず結果未確認にする', async () => {
    oldAuth()
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{', { headers: { 'Content-Type': 'application/json' } }),
    )
    expect(await login(credentials)).toEqual({
      status: 'verification-unknown',
      authEpoch: useAuthStore().authEpoch,
    })
    empty()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it.each(['login', 'logout'] as const)(
    '遅延%s成功でCookieが変わると新世代も未確認に戻し明示GETだけを許す',
    async (kind) => {
      const auth = oldAuth(),
        pending = deferred<Response>()
      let cookie = b
      vi.mocked(fetch).mockImplementationOnce(() => pending.promise)
      const work = kind === 'login' ? login(credentials) : logout()
      auth.signIn({ teamName: 'B', teamId: b })
      queryClient.setQueryData(['B'], 'B秘密')
      const epoch = auth.authEpoch
      cookie = kind === 'login' ? a : ''
      pending.resolve(
        response({ status: kind === 'login' ? 'authenticated' : 'logged_out' }),
      )
      expect(await work).toEqual({
        status: 'verification-unknown',
        authEpoch: epoch + 1,
      })
      empty()
      expect(auth.sessionExpired).toBe(false)
      await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(
        ApiSessionUnverifiedError,
      )
      expect(await ensureSessionVerified()).toEqual({
        status: 'verification-unknown',
        authEpoch: auth.authEpoch,
      })
      expect(fetch).toHaveBeenCalledTimes(1)
      respond(
        cookie ? { tenant_id: cookie, team_name: '実Cookieの名称' } : {},
        cookie ? 200 : 401,
      )
      const checked = await session()
      expect(checked.status).toBe(
        cookie ? 'authenticated' : 'server-unauthenticated',
      )
      expect(auth.teamId).toBe(cookie || null)
      expect(vi.mocked(fetch).mock.calls.map((c) => c[1]?.method)).toEqual([
        'POST',
        'GET',
      ])
    },
  )
  it.each(['login', 'logout'] as const)(
    '遅延%sの確定非2xxは新世代を無効化しない',
    async (kind) => {
      const auth = oldAuth(),
        pending = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(pending.promise)
      const work = kind === 'login' ? login(credentials) : logout()
      auth.signIn({ teamName: 'B', teamId: b })
      queryClient.setQueryData(['B'], 'B秘密')
      const epoch = auth.authEpoch
      pending.resolve(response({}, 401))
      expect(await work).toMatchObject({ status: 'stale' })
      expect(auth.authEpoch).toBe(epoch)
      expect(auth.teamId).toBe(b)
      expect(queryClient.getQueryData(['B'])).toBe('B秘密')
    },
  )
  it.each(['login', 'logout'] as const)(
    '遅延%sの成功headersは本文を読まず一度だけ無効化する',
    async (kind) => {
      const auth = oldAuth(),
        pending = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(pending.promise)
      const work = kind === 'login' ? login(credentials) : logout()
      auth.signIn({ teamName: 'B', teamId: b })
      const clear = vi.spyOn(queryClient, 'clear'),
        discard = vi.spyOn(auth, 'beginSessionVerification')
      const epoch = auth.authEpoch
      const readBody = vi.fn().mockRejectedValue(new Error('body lost'))
      pending.resolve({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: readBody,
      } as unknown as Response)
      const result = await work
      expect(readBody).not.toHaveBeenCalled()
      expect(result).toEqual({
        status: 'verification-unknown',
        authEpoch: epoch + 1,
      })
      expect(await ensureSessionVerified()).toEqual(result)
      expect(await ensureSessionVerified()).toEqual(result)
      expect(discard).toHaveBeenCalledTimes(1)
      expect(clear).toHaveBeenCalledTimes(1)
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it.each([
    ['login', true],
    ['login', false],
    ['logout', true],
    ['logout', false],
  ] as const)(
    'session再確認と旧%sの到着順(session先=%s)によらずCookie変更後は未確認',
    async (kind, sessionFirst) => {
      const auth = oldAuth(),
        old = deferred<Response>(),
        check = deferred<Response>()
      vi.mocked(fetch)
        .mockReturnValueOnce(old.promise)
        .mockReturnValueOnce(check.promise)
      const mutation = kind === 'login' ? login(credentials) : logout()
      auth.signIn({ teamName: 'B', teamId: b })
      const checking = session()
      if (sessionFirst) {
        check.resolve(response({ tenant_id: b, team_name: 'B' }))
        expect((await checking).status).toBe('authenticated')
      }
      old.resolve(
        response({ status: kind === 'login' ? 'authenticated' : 'logged_out' }),
      )
      expect((await mutation).status).toBe('verification-unknown')
      if (!sessionFirst) {
        check.resolve(response({ tenant_id: b, team_name: 'B' }))
        expect((await checking).status).toBe('stale')
      }
      empty()
      expect((await ensureSessionVerified()).status).toBe(
        'verification-unknown',
      )
      expect(fetch).toHaveBeenCalledTimes(2)
    },
  )
  it('複数世代の旧login/logoutは各Cookie変更時に無効化するだけで旧tenantを採らない', async () => {
    const auth = oldAuth(),
      oldLogin = deferred<Response>(),
      oldLogout = deferred<Response>()
    vi.mocked(fetch)
      .mockReturnValueOnce(oldLogin.promise)
      .mockReturnValueOnce(oldLogout.promise)
    const first = login(credentials)
    auth.signIn({ teamName: 'B', teamId: b })
    const second = logout()
    auth.signIn({ teamName: '次世代B', teamId: b })
    oldLogin.resolve(response({ status: 'authenticated' }))
    expect((await first).status).toBe('verification-unknown')
    empty()
    respond({ tenant_id: b, team_name: '再確認B' })
    expect((await session()).status).toBe('authenticated')
    queryClient.setQueryData(['B'], '再確認後B秘密')
    oldLogout.resolve(response({ status: 'logged_out' }))
    expect((await second).status).toBe('verification-unknown')
    empty()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it.each(['login', 'logout'] as const)(
    '遅延%sの通信結果不明は通知と破棄を一度だけ行う',
    async (kind) => {
      const auth = oldAuth(),
        pending = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(pending.promise)
      const work = kind === 'login' ? login(credentials) : logout()
      auth.signIn({ teamName: 'B', teamId: b })
      const discard = vi.spyOn(auth, 'beginSessionVerification')
      pending.reject(new DOMException('cancel', 'AbortError'))
      const result = await work
      expect(result.status).toBe('verification-unknown')
      expect(await ensureSessionVerified()).toEqual(result)
      expect(discard).toHaveBeenCalledTimes(1)
      empty()
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it.each(['login', 'logout'] as const)(
    '現世代%sの成功headers後の本文失敗も一応答で二重破棄しない',
    async (kind) => {
      const auth = oldAuth()
      const clear = vi.spyOn(queryClient, 'clear')
      const discard = vi.spyOn(auth, 'beginSessionVerification')
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers(),
        text: vi.fn().mockRejectedValue(new Error('body lost')),
      } as unknown as Response)
      const result = await (kind === 'login' ? login(credentials) : logout())
      expect(result.status).toBe('verification-unknown')
      expect(await ensureSessionVerified()).toEqual(result)
      expect(discard).toHaveBeenCalledTimes(1)
      expect(clear).toHaveBeenCalledTimes(1)
      empty()
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
})

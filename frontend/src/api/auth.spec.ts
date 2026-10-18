import { setVerifiedAuthForTest } from './auth.test-support'
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
import {
  AUTH_INTENT_KEY,
  readAuthIntent,
  withAuthIntent,
  writeAuthIntent,
  type AuthIntent,
} from './authIntent'
import { ApiSessionUnverifiedError, apiRequest } from './client'

const a = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const b = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const credentials = { team_name: '入力値', password: 'test-only' }
let pinia: Pinia
let pins: Pinia[]
function tab() {
  const p = createPinia()
  pins.push(p)
  setActivePinia(p)
  return p
}
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
async function intent(
  phase: AuthIntent['phase'] = 'expected',
  id: string | null = b,
) {
  return withAuthIntent(() => writeAuthIntent(phase, id))
}
function empty(p = pinia) {
  const auth = useAuthStore(p)
  expect(auth.isAuthenticated).toBe(false)
  expect(auth.teamId).toBeNull()
  expect(auth.teamName).toBeNull()
  expect(queryClient.getQueryCache().getAll()).toEqual([])
}
function oldAuth() {
  const auth = useAuthStore()
  setVerifiedAuthForTest(auth, { teamName: '旧A', teamId: a })
  queryClient.setQueryData(['old'], 'A秘密')
  return auth
}
async function loggedIn(id = b) {
  respond({ status: 'authenticated', tenant_id: id })
  respond({ tenant_id: id, team_name: '正規名' })
  expect((await login(credentials)).status).toBe('authenticated')
  return useAuthStore()
}
beforeEach(() => {
  pins = []
  localStorage.clear()
  queryClient.clear()
  pinia = tab()
  vi.stubGlobal('fetch', vi.fn())
  // 単体試験のlock。実ブラウザの排他・Cookie適用試験とは区別する。
  vi.stubGlobal('navigator', {
    locks: {
      request: vi.fn(async (_name, _options, action) =>
        action({ name: 'test' }),
      ),
    },
  })
})
afterEach(() => {
  for (const p of pins) disposePinia(p)
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('承認済みlogin/session相関', () => {
  it('保存AやCookieだけでは復帰せず、意図なしは通信0', async () => {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        sessionId: a,
        teamName: '保存A',
        teamId: a,
      }),
    )
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    empty()
    await expect(apiRequest('GET', '/players')).rejects.toBeInstanceOf(
      ApiSessionUnverifiedError,
    )
    expect(fetch).not.toHaveBeenCalled()
  })
  it('loginの検証済みIDとsessionだけが認証済みになり、入力名は表示に使わない', async () => {
    const auth = await loggedIn()
    expect(auth.teamId).toBe(b)
    expect(auth.teamName).toBe('正規名')
    expect(vi.mocked(fetch).mock.calls.map((c) => c[1]?.method)).toEqual([
      'POST',
      'GET',
    ])
    expect(readAuthIntent()).toMatchObject({ phase: 'expected', tenantId: b })
    expect(localStorage.getItem(AUTH_INTENT_KEY)).not.toContain(
      credentials.password,
    )
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.credentials).toBe('include')
  })
  it.each([401, 422, 429, 500, 503])(
    'login %sは旧store/cacheを復元しない',
    async (status) => {
      oldAuth()
      respond({}, status)
      const result = await login(credentials)
      expect(result.status).toBe(
        status === 401 || status === 429 ? 'rejected' : 'verification-unknown',
      )
      empty()
      expect(readAuthIntent()).toMatchObject({
        phase: 'verification-required',
        tenantId: null,
      })
      expect(fetch).toHaveBeenCalledTimes(1)
      await session()
      await ensureSessionVerified()
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it('POSTを開始する前に旧cacheを消し、本文とsession確認中はtenant通信を拒否', async () => {
    const auth = oldAuth(),
      body = deferred<string>(),
      check = deferred<Response>()
    vi.mocked(fetch)
      .mockImplementationOnce(async () => {
        empty()
        expect(readAuthIntent()?.phase).toBe('pending')
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          text: () => body.promise,
        } as Response
      })
      .mockReturnValueOnce(check.promise)
    const work = login(credentials)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    expect(auth.isAuthenticated).toBe(false)
    await expect(
      apiRequest('POST', '/players', { body: {} }),
    ).rejects.toBeInstanceOf(ApiSessionUnverifiedError)
    body.resolve(JSON.stringify({ status: 'authenticated', tenant_id: b }))
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    empty()
    check.resolve(response({ tenant_id: b, team_name: '正規B' }))
    expect((await work).status).toBe('authenticated')
  })
  it.each([
    {},
    null,
    [],
    { status: 'authenticated' },
    { status: 'authenticated', tenant_id: 'bad' },
    { status: 'authenticated', tenant_id: b.toUpperCase() },
    { status: 'authenticated', tenant_id: b, token: 'forbidden' },
  ])('不正login DTO %jはsessionを送らない', async (value) => {
    oldAuth()
    respond(value)
    expect((await login(credentials)).status).toBe('verification-unknown')
    empty()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(readAuthIntent()?.tenantId).toBeNull()
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
    { tenant_id: a, team_name: '別A' },
  ])('不正・異tenant session DTO %jを採らない', async (value) => {
    await intent()
    respond(value)
    expect((await session()).status).toBe('verification-unknown')
    empty()
    expect(readAuthIntent()).toMatchObject({
      phase: 'verification-required',
      tenantId: b,
    })
  })
  it.each([404, 422, 429, 500, 503])(
    'session %sは未認証と区別し明示GETだけで再確認',
    async (status) => {
      await intent()
      respond({}, status)
      expect((await ensureSessionVerified()).status).toBe(
        'verification-unknown',
      )
      expect((await ensureSessionVerified()).status).toBe(
        'verification-unknown',
      )
      expect(fetch).toHaveBeenCalledTimes(1)
      respond({ tenant_id: b, team_name: 'B' })
      expect((await session()).status).toBe('authenticated')
      expect(vi.mocked(fetch).mock.calls.map((c) => c[1]?.method)).toEqual([
        'GET',
        'GET',
      ])
    },
  )
  it('session401はsigned-outにし、自動復帰しない', async () => {
    await intent()
    respond({}, 401)
    expect((await session()).status).toBe('server-unauthenticated')
    expect(readAuthIntent()?.phase).toBe('signed-out')
    await ensureSessionVerified()
    expect(fetch).toHaveBeenCalledTimes(1)
    empty()
  })
  it.each([new TypeError('offline'), new DOMException('cancel', 'AbortError')])(
    '結果不明loginは資格情報も未知tenantのGETも自動再送しない',
    async (error) => {
      oldAuth()
      vi.mocked(fetch).mockRejectedValueOnce(error)
      expect((await login(credentials)).status).toBe('verification-unknown')
      empty()
      await session()
      await ensureSessionVerified()
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it('不正JSONも成功にならず、旧cacheを復元しない', async () => {
    oldAuth()
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{', { headers: { 'Content-Type': 'application/json' } }),
    )
    expect((await login(credentials)).status).toBe('verification-unknown')
    empty()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('同時sessionを1要求に集約し、確認済みなら再送しない', async () => {
    await intent()
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const one = ensureSessionVerified(),
      two = ensureSessionVerified()
    expect(one).toBe(two)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    p.resolve(response({ tenant_id: b, team_name: 'B' }))
    await one
    await ensureSessionVerified()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('login中は二重login/session/logoutを拒否する', async () => {
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const work = login(credentials)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    await expect(login(credentials)).rejects.toBeInstanceOf(
      AuthOperationInProgressError,
    )
    await expect(session()).rejects.toBeInstanceOf(AuthOperationInProgressError)
    await expect(logout()).rejects.toBeInstanceOf(AuthOperationInProgressError)
    p.resolve(response({}, 401))
    await work
  })
  it('session中はloginを開始しない', async () => {
    await intent()
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const check = session()
    await expect(login(credentials)).rejects.toBeInstanceOf(
      AuthOperationInProgressError,
    )
    p.resolve(response({ tenant_id: b, team_name: 'B' }))
    await check
  })
  it('同tenantの新タブ/reloadの確認は意図・旧タブ認証を変更しない（P1-1）', async () => {
    const first = await loggedIn(),
      marker = localStorage.getItem(AUTH_INTENT_KEY)
    const epoch = first.authEpoch
    tab()
    respond({ tenant_id: b, team_name: 'B' })
    expect((await ensureSessionVerified()).status).toBe('authenticated')
    expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
    first.syncFromStorage()
    expect(first.isAuthenticated).toBe(true)
    expect(first.authEpoch).toBe(epoch)
  })
  it('別タブlogin後、旧タブは新tenantを自動採用しない（P1-2）', async () => {
    const first = await loggedIn(a)
    tab()
    await loggedIn(b)
    setActivePinia(pinia)
    first.syncFromStorage()
    expect(first.explicitLoginRequired).toBe(true)
    const before = vi.mocked(fetch).mock.calls.length
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    expect((await session()).status).toBe('verification-unknown')
    expect(fetch).toHaveBeenCalledTimes(before)
    expect(first.teamId).toBeNull()
  })
  it.each(['login', 'logout'] as const)(
    '旧%sの成功headersは新意図を未確認化し、本文を採らず通知は一度',
    async (kind) => {
      await loggedIn(a)
      const p = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(p.promise)
      const old = kind === 'login' ? login(credentials) : logout()
      await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
      tab()
      const newer = await loggedIn(b)
      queryClient.setQueryData(['new'], 'B秘密')
      const text = vi.fn().mockRejectedValue(new Error('body lost'))
      const clear = vi.spyOn(queryClient, 'clear')
      p.resolve({
        ok: true,
        status: 200,
        headers: new Headers(),
        text,
      } as unknown as Response)
      expect((await old).status).toBe('stale')
      expect(text).not.toHaveBeenCalled()
      expect(readAuthIntent()).toMatchObject({
        phase: 'verification-required',
        tenantId: b,
      })
      expect(clear).toHaveBeenCalledTimes(1)
      newer.syncFromStorage()
      expect(newer.isAuthenticated).toBe(false)
      expect(queryClient.getQueryCache().getAll()).toEqual([])
    },
  )
  it.each(['login', 'logout'] as const)(
    '旧%sの確定非2xxは新tenantを無効化しない',
    async (kind) => {
      await loggedIn(a)
      const p = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(p.promise)
      const old = kind === 'login' ? login(credentials) : logout()
      await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
      tab()
      const newer = await loggedIn(b),
        marker = localStorage.getItem(AUTH_INTENT_KEY)
      p.resolve(response({}, 401))
      expect((await old).status).toBe('stale')
      expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
      newer.syncFromStorage()
      expect(newer.teamId).toBe(b)
    },
  )
  it.each(['login', 'logout'] as const)(
    '旧%sの通信結果不明は現在意図を安全側へ一度だけ無効化',
    async (kind) => {
      await loggedIn(a)
      const p = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(p.promise)
      const old = kind === 'login' ? login(credentials) : logout()
      await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
      tab()
      await loggedIn(b)
      p.reject(new TypeError('offline'))
      await old
      expect(readAuthIntent()).toMatchObject({
        phase: 'verification-required',
        tenantId: b,
      })
      const marker = localStorage.getItem(AUTH_INTENT_KEY)
      setActivePinia(pinia)
      await ensureSessionVerified()
      expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
      expect(useAuthStore().teamId).toBeNull()
    },
  )
  it('旧session成功もCookieが変わり得るので新意図を未確認へ戻す', async () => {
    await intent('expected', a)
    const p = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(p.promise)
    const old = session()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    tab()
    await loggedIn(b)
    p.resolve(response({ tenant_id: a, team_name: '旧A' }))
    expect((await old).status).toBe('stale')
    expect(readAuthIntent()).toMatchObject({
      phase: 'verification-required',
      tenantId: b,
    })
  })
  it('login本文待ちで意図が変われば旧ackを採らない', async () => {
    const body = deferred<string>()
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: () => body.promise,
    } as Response)
    const old = login(credentials)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    tab()
    await loggedIn(b)
    const marker = localStorage.getItem(AUTH_INTENT_KEY)
    body.resolve(JSON.stringify({ status: 'authenticated', tenant_id: a }))
    expect((await old).status).toBe('stale')
    expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
  })
  it.each([200, 401])(
    'logout %sはtombstoneを残しGETによる自動復帰を禁止',
    async (status) => {
      await loggedIn()
      respond(status === 200 ? { status: 'logged_out' } : {}, status)
      expect((await logout()).status).toBe('logged-out')
      empty()
      const before = vi.mocked(fetch).mock.calls.length
      await session()
      await ensureSessionVerified()
      expect(fetch).toHaveBeenCalledTimes(before)
      expect(readAuthIntent()).toMatchObject({
        phase: 'signed-out',
        tenantId: null,
      })
    },
  )
  it.each([500, 200])('logout不正%sは未確認で再送なし', async (status) => {
    await loggedIn()
    respond({}, status)
    expect((await logout()).status).toBe('verification-unknown')
    empty()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it.each(['lock-unavailable', 'lock-busy', 'storage-unavailable'] as const)(
    '%sでは旧認証を破棄し通信0、理由を保持',
    async (reason) => {
      const auth = oldAuth()
      if (reason === 'lock-unavailable') vi.stubGlobal('navigator', {})
      else if (reason === 'lock-busy')
        vi.mocked(navigator.locks.request).mockImplementation(
          async (_n, _o, cb) => cb!(null),
        )
      else
        vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
          throw new Error('denied')
        })
      expect((await login(credentials)).status).toBe('verification-unknown')
      expect(auth.environmentReason).toBe(reason)
      empty()
      expect(fetch).not.toHaveBeenCalled()
    },
  )
})

describe('第1周の回復・直列化指摘', () => {
  it('成功本文は非同期Cookie通知の完了まで読まない', async () => {
    const waiting = deferred<void>()
    const text = vi
      .fn()
      .mockResolvedValue(
        JSON.stringify({ status: 'authenticated', tenant_id: b }),
      )
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text,
    } as unknown as Response)
    const notify = vi.fn(() => waiting.promise)
    const work = apiRequest('POST', '/auth/login', {
      body: credentials,
      noAuthExpiry: true,
      onAuthCookieUncertain: notify,
    })
    await vi.waitFor(() => expect(notify).toHaveBeenCalledTimes(1))
    expect(text).not.toHaveBeenCalled()
    waiting.resolve()
    await work
    expect(text).toHaveBeenCalledTimes(1)
  })
  it('lock-busy後は他タブの意図を変更せず明示GETで回復', async () => {
    const marker = await intent()
    vi.mocked(navigator.locks.request).mockImplementationOnce(
      async (_n, _o, action) => action!(null),
    )
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    const auth = useAuthStore()
    expect(auth.environmentReason).toBe('lock-busy')
    expect(auth.canReverify).toBe(true)
    expect(auth.explicitLoginRequired).toBe(false)
    expect(fetch).not.toHaveBeenCalled()
    respond({ tenant_id: b, team_name: 'B' })
    expect((await session()).status).toBe('authenticated')
    expect(readAuthIntent()).toEqual(marker)
    expect(auth.environmentReason).toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('同tenantの別タブ再loginも旧タブは自動復帰せず明示GETだけを許す', async () => {
    const first = await loggedIn(b)
    tab()
    await loggedIn(b)
    setActivePinia(pinia)
    first.syncFromStorage()
    const count = vi.mocked(fetch).mock.calls.length
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    expect(fetch).toHaveBeenCalledTimes(count)
    expect(first.canReverify).toBe(true)
    respond({ tenant_id: b, team_name: 'B' })
    expect((await session()).status).toBe('authenticated')
    expect(fetch).toHaveBeenCalledTimes(count + 1)
  })
  it('非同期付与と排他を伴うlockでもlogin/logoutの成功が自己競合しない', async () => {
    let held = false
    vi.mocked(navigator.locks.request).mockImplementation(
      async (_n, _o, action) => {
        await Promise.resolve()
        if (held) return action!(null)
        held = true
        try {
          return action!({ name: 'native-like' } as Lock)
        } finally {
          held = false
        }
      },
    )
    await loggedIn()
    respond({ status: 'logged_out' })
    expect((await logout()).status).toBe('logged-out')
    expect(useAuthStore().environmentReason).toBeNull()
  })
})

describe('通常tenant応答のCookie更新と本文遅延の区別', () => {
  it('旧tenantのheadersが新認証後に届けば本文を読まず未確認にする', async () => {
    const auth = oldAuth(),
      pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    const work = apiRequest('GET', '/team-records')
    setVerifiedAuthForTest(auth, { teamId: b, teamName: 'B' })
    queryClient.setQueryData(['B'], 'B秘密')
    const res = response({ items: [], next_cursor: null }),
      read = vi.spyOn(res, 'text')
    pending.resolve(res)
    await expect(work).rejects.toMatchObject({ name: 'ApiStaleAuthError' })
    expect(read).not.toHaveBeenCalled()
    empty()
    expect(readAuthIntent()).toMatchObject({
      phase: 'verification-required',
      tenantId: b,
    })
  })
  it('sessionのheadersは旧世代で観測済みで本文だけ遅延した場合は新Bを壊さない', async () => {
    await intent('expected', a)
    const body = deferred<string>(),
      read = vi.fn(() => body.promise)
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: read,
    } as unknown as Response)
    const old = session()
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    // 同じアプリ世代でBを確定する。別タブのqueryClientは別JS realmである。
    const newer = useAuthStore(pinia)
    setVerifiedAuthForTest(newer, { teamId: b, teamName: 'B' })
    queryClient.setQueryData(['B'], 'B秘密')
    const marker = localStorage.getItem(AUTH_INTENT_KEY)
    body.resolve(JSON.stringify({ tenant_id: a, team_name: '旧A' }))
    expect((await old).status).toBe('stale')
    expect(newer.isAuthenticated).toBe(true)
    expect(queryClient.getQueryData(['B'])).toBe('B秘密')
    expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
  })
  it('別の旧Cookie通知は未確認中でも新しい意図で確認待ちsessionを拒否する', async () => {
    const auth = await loggedIn(b)
    await auth.invalidateUncertainCookie()
    const first = readAuthIntent()!
    const body = deferred<string>(),
      read = vi.fn(() => body.promise)
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: read,
    } as unknown as Response)
    const checking = session()
    await vi.waitFor(() => expect(read).toHaveBeenCalledTimes(1))
    await auth.invalidateUncertainCookie()
    expect(readAuthIntent()!.intentId).not.toBe(first.intentId)
    body.resolve(JSON.stringify({ tenant_id: b, team_name: 'B' }))
    expect((await checking).status).toBe('stale')
    empty()
  })
})

describe('拒否通知とsession採用の前後競合', () => {
  it('通知の未ackで自動GETを止め、明示server確認に成功したタブだけ回復する', async () => {
    const auth = await loggedIn()
    queryClient.setQueryData(['B'], 'private')
    await auth.invalidateUncertainCookie()
    vi.mocked(fetch).mockClear()
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    expect(fetch).not.toHaveBeenCalled()
    empty()
    respond({ tenant_id: b, team_name: '正規B' })
    expect((await session()).status).toBe('authenticated')
    expect(localStorage.getItem('bb.auth.uncertain.ack')).toBe(
      localStorage.getItem('bb.auth.uncertain'),
    )
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('確認中に新通知とそのackが揃っても旧sessionを採用しない', async () => {
    const auth = await loggedIn()
    await auth.invalidateUncertainCookie()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const checking = session()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
    localStorage.setItem('bb.auth.uncertain', a)
    localStorage.setItem('bb.auth.uncertain.ack', a)
    waiting.resolve(response({ tenant_id: b, team_name: '旧確認B' }))
    expect((await checking).status).not.toBe('authenticated')
    empty()
  })
  it('lock保持中に古いloginが届いてもlock待ちせず拒否通知を出す', async () => {
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const old = login(credentials)
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    await intent('expected', b)
    const nextTab = tab()
    const newer = useAuthStore(nextTab)
    // 実server確認成功を準備する単体fixture。通知後に再採用はしない。
    setVerifiedAuthForTest(newer, { teamName: '新B', teamId: b })
    queryClient.setQueryData(['B'], 'private')
    vi.stubGlobal('navigator', {
      locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
    })
    waiting.resolve(response({ status: 'authenticated', tenant_id: a }))
    expect((await old).status).not.toBe('authenticated')
    expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
    newer.syncFromStorage()
    empty(nextTab)
    expect(newer.automaticVerificationBlocked).toBe(true)
  })
  it.each(['bb.auth.uncertain', 'bb.auth.uncertain.ack'])(
    '破損した%sは明示loginと実session確認を経てだけ回復',
    async (key) => {
      await loggedIn()
      localStorage.setItem(key, 'corrupt')
      useAuthStore().syncFromStorage()
      empty()
      vi.mocked(fetch).mockClear()
      await ensureSessionVerified()
      expect(fetch).not.toHaveBeenCalled()
      respond({ status: 'authenticated', tenant_id: b })
      respond({ tenant_id: b, team_name: '正規B' })
      expect((await login(credentials)).status).toBe('authenticated')
      expect(fetch).toHaveBeenCalledTimes(2)
    },
  )
})

it.each(['malformed', null])(
  'session確認中にackが%sへ壊れたら採用しない',
  async (raw) => {
    const auth = await loggedIn()
    await auth.invalidateUncertainCookie()
    respond({ tenant_id: b, team_name: '正規B' })
    expect((await session()).status).toBe('authenticated')
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const checking = session()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(4))
    if (raw === null) localStorage.removeItem('bb.auth.uncertain.ack')
    else localStorage.setItem('bb.auth.uncertain.ack', raw)
    waiting.resolve(response({ tenant_id: b, team_name: '遅れたB' }))
    expect((await checking).status).not.toBe('authenticated')
    empty()
  },
)

it.each(['session', 'login', 'logout'] as const)(
  '現行%sの結果不明もlock競合中に一度通知する',
  async (kind) => {
    await loggedIn()
    vi.mocked(fetch).mockClear()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const writes = vi.spyOn(Storage.prototype, 'setItem')
    const operation =
      kind === 'login'
        ? login(credentials)
        : kind === 'logout'
          ? logout()
          : session()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    vi.stubGlobal('navigator', {
      locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
    })
    waiting.reject(new TypeError('network'))
    expect((await operation).status).not.toBe('authenticated')
    empty()
    expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
    expect(
      writes.mock.calls.filter(([key]) => key === 'bb.auth.uncertain'),
    ).toHaveLength(1)
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)

it.each([false, true])(
  '旧password応答をlock競合%sでも新世代へ採用せず失効通知する',
  async (busy) => {
    oldAuth()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const old = apiRequest('PATCH', '/auth/password', { body: {} })
    setVerifiedAuthForTest(useAuthStore(), { teamName: '新B', teamId: b })
    queryClient.setQueryData(['new-B'], 'private')
    if (busy)
      vi.stubGlobal('navigator', {
        locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
      })
    waiting.resolve(response({ status: 'password_changed' }))
    await expect(old).rejects.toMatchObject({ name: 'ApiStaleAuthError' })
    empty()
    expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)

it.each(['dto', 'body', 'http'] as const)(
  'sessionの%s未確認もlock競合時に拒否通知し、成功を採らない',
  async (failure) => {
    await loggedIn()
    vi.mocked(fetch).mockClear()
    const waiting = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(waiting.promise)
    const operation = session()
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))
    vi.stubGlobal('navigator', {
      locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
    })
    const res =
      failure === 'dto'
        ? response({ tenant_id: a, team_name: '異tenant' })
        : failure === 'http'
          ? response({}, 503)
          : response({})
    if (failure === 'body')
      vi.spyOn(res, 'text').mockRejectedValue(new TypeError('transport'))
    waiting.resolve(res)
    expect((await operation).status).not.toBe('authenticated')
    empty()
    expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)

it.each(['pending', 'corrupt'] as const)(
  'reload時の%s通知では自動GETせず明示server確認だけで回復',
  async (state) => {
    const auth = await loggedIn()
    await auth.invalidateUncertainCookie()
    if (state === 'corrupt') localStorage.setItem('bb.auth.uncertain', 'bad')
    const next = tab()
    const reloaded = useAuthStore(next)
    expect(reloaded.automaticVerificationBlocked).toBe(true)
    vi.mocked(fetch).mockClear()
    expect((await ensureSessionVerified()).status).toBe('verification-unknown')
    expect(fetch).not.toHaveBeenCalled()
    expect(reloaded.canReverify).toBe(true)
    respond({ tenant_id: b, team_name: '正規B' })
    expect((await session()).status).toBe('authenticated')
    expect(localStorage.getItem('bb.auth.uncertain.ack')).toBe(
      localStorage.getItem('bb.auth.uncertain'),
    )
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)

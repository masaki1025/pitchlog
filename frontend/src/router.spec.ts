import { setVerifiedAuthForTest } from './api/auth.test-support'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import * as authApi from './api/auth'
import StrikeZoneCompareHost from './components/zone/StrikeZoneCompareHost.vue'
import type { Plugin } from 'vue'
import { createMemoryHistory, createWebHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import { installAppProviders, pinia } from './appProviders'
import { queryClient } from './lib/queryClient'
import { rosterQueryKeys } from './lib/rosterQueryKeys'
import { createAppRouter } from './router'
import TeamScreen from './screens/TeamScreen.vue'
import { AUTH_STORAGE_KEY, useAuthStore } from './stores/authStore'

const sharedProviders: Plugin = { install: installAppProviders }
const tenantA = '12345678-1234-4234-8234-123456789abc'
const tenantB = '22345678-1234-4234-8234-123456789abc'
const wrappers: VueWrapper[] = []
const fetchMock = vi.fn<typeof fetch>()
const reply = (body: unknown, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
const routePath = (url: RequestInfo | URL) =>
  new URL(String(url), 'http://localhost').pathname
const rosterCalls = (
  path: '/api/team-records/self' | '/api/team-records',
  tenantId?: string,
) =>
  fetchMock.mock.calls.filter(
    ([url, init]) =>
      routePath(url) === path &&
      (tenantId === undefined ||
        new Headers(init?.headers).get('X-Pitchlog-Expected-Tenant') ===
          tenantId),
  )
function rosterReply(url: RequestInfo | URL, init?: RequestInit, id = tenantA) {
  const path = routePath(url)
  if (
    path !== '/api/team-records/self' &&
    path !== '/api/team-records' &&
    path !== '/api/players'
  )
    throw new Error(`想定外のroster経路: ${path}`)
  const body =
    path === '/api/team-records/self'
      ? { id, kind: 'self', name: 'チーム', hidden_at: null }
      : { items: [], next_cursor: null }
  const headers = new Headers(init?.headers)
  return reply(body, 200, {
    'X-Pitchlog-Tenant-Match': '1',
    'X-Pitchlog-Tenant-Challenge':
      headers.get('X-Pitchlog-Tenant-Challenge') ?? '',
  })
}
function deferred() {
  let resolve!: (value: Response) => void
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function view(router: ReturnType<typeof createAppRouter>) {
  const wrapper = mount(App, { global: { plugins: [sharedProviders, router] } })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('navigator', {
    locks: {
      request: vi.fn(async (_n, _o, action) =>
        action({ name: 'integration-unit' }),
      ),
    },
  })
  const auth = useAuthStore(pinia)
  setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'fixture-A' })
  auth.beginSessionVerification()
  queryClient.clear()
  fetchMock.mockReset().mockImplementation(async () => reply({}, 401))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  useAuthStore(pinia).hasHydrated = true
  useAuthStore(pinia).signOut()
  queryClient.clear()
  vi.restoreAllMocks()
  window.history.replaceState({}, '', '/')
  vi.unstubAllGlobals()
})

describe('公開ガイドと保護チーム経路', () => {
  it('未ログインでも/helpへ直接到達し、tenant通信をしない', async () => {
    window.history.replaceState({}, '', '/help')
    const router = createAppRouter(createWebHistory())
    const wrapper = view(router)
    await router.isReady()
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe('使い方')
    expect(router.currentRoute.value.name).toBe('help')
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('トップとガイドを往復してもproviderは同一でtenant通信なし', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    const wrapper = view(router)
    const auth = useAuthStore(pinia)
    const cache = queryClient
    await wrapper.get('a[aria-label="使い方を開く"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="戻る"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('home')
    expect(useAuthStore(pinia)).toBe(auth)
    expect(queryClient).toBe(cache)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it.each([401, 500])(
    'session %iでは/teamを描画せず/loginへ移す',
    async (status) => {
      fetchMock.mockResolvedValue(reply({}, status))
      const router = createAppRouter(createMemoryHistory())
      await router.push('/team')
      const wrapper = view(router)
      await flushPromises()
      expect(router.currentRoute.value.fullPath).toBe('/login?redirect=/team')
      expect(wrapper.findComponent(TeamScreen).exists()).toBe(false)
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/auth/session')
      expect(useAuthStore(pinia).isAuthenticated).toBe(false)
      if (status === 500)
        expect(wrapper.text()).toContain('認証状態を確認できません')
    },
  )
  it('hydrationとsessionのDTO検証前は保護画面/APIを開始しない', async () => {
    const auth = useAuthStore(pinia)
    auth.hasHydrated = false
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    const router = createAppRouter(createMemoryHistory())
    const navigating = router.push('/team')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    auth.hasHydrated = true
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(auth.isAuthenticated).toBe(false)
    pending.resolve(reply({ tenant_id: tenantA, team_name: 'チームA' }))
    await navigating
    expect(router.currentRoute.value.name).toBe('team')
    expect(auth.teamId).toBe(tenantA)
    // guardだけの検査なので一覧画面はまだmountせず、roster要求は0件。
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it.each([
    { tenant_id: tenantA },
    { tenant_id: '推測tenant', team_name: 'チームA' },
    { tenant_id: tenantA, team_name: '' },
  ])('session不正DTOを認証済みにしない: %j', async (dto) => {
    fetchMock.mockResolvedValue(reply(dto))
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAuthStore(pinia).isAuthenticated).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('session待ちの認証切替では旧結果を採らずtenant通信をしない', async () => {
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    const router = createAppRouter(createMemoryHistory())
    const navigating = router.push('/team')
    await flushPromises()
    useAuthStore(pinia).signOut()
    pending.resolve(reply({ tenant_id: tenantA, team_name: '旧A' }))
    await navigating
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAuthStore(pinia).teamId).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('通信失敗は未確認として移し、資格情報や変更要求を再送しない', async () => {
    fetchMock.mockRejectedValue(new TypeError('通信失敗'))
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.text()).toContain('認証状態を確認できません')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
  it('認証切替でTeamScreenを再生成し、旧cacheを保持しない', async () => {
    fetchMock.mockImplementation(async (url, init) =>
      rosterReply(
        url,
        init,
        new Headers(init?.headers).get('X-Pitchlog-Expected-Tenant') ?? tenantA,
      ),
    )
    const auth = useAuthStore(pinia)
    setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'A' })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    const oldScreen = wrapper.getComponent(TeamScreen).vm.$.uid
    queryClient.setQueryData(['old-tenant-marker'], '旧A')
    setVerifiedAuthForTest(auth, { teamId: tenantB, teamName: 'B' })
    await flushPromises()
    expect(wrapper.getComponent(TeamScreen).vm.$.uid).not.toBe(oldScreen)
    expect(queryClient.getQueryData(['old-tenant-marker'])).toBeUndefined()
    expect(useAuthStore(pinia)).toBe(auth)
    auth.signOut()
    await flushPromises()
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
  })
  it.each(['https://example.invalid', '//example.invalid', '/unfinished'])(
    'loginの不正な戻り先%sを使わない',
    async (redirect) => {
      const router = createAppRouter(createMemoryHistory())
      await router.push({ name: 'login', query: { redirect } })
      const wrapper = view(router)
      await flushPromises()
      fetchMock.mockImplementation(async (url, init) => {
        if (String(url).endsWith('/auth/login'))
          return reply({ status: 'authenticated', tenant_id: tenantA })
        if (String(url).endsWith('/auth/session'))
          return reply({ tenant_id: tenantA, team_name: 'A' })
        return rosterReply(url, init)
      })
      await wrapper.get('input[name="team_name"]').setValue('A')
      await wrapper.get('input[name="password"]').setValue('test-password')
      await wrapper.get('form').trigger('submit')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/team')
      expect(wrapper.findComponent(TeamScreen).exists()).toBe(true)
    },
  )
  it('実clientのlogin ack後もsession確認が終わるまで画面/一覧を開始しない', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/login?redirect=/team')
    const wrapper = view(router)
    await flushPromises()
    const pending = deferred()
    fetchMock.mockClear()
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith('/auth/login'))
        return reply({ status: 'authenticated', tenant_id: tenantA })
      if (String(url).endsWith('/auth/session')) return pending.promise
      return rosterReply(url, init)
    })
    await wrapper.get('input[name="team_name"]').setValue('A')
    await wrapper.get('input[name="password"]').setValue('test-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(false)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/auth/login',
      '/api/auth/session',
    ])
    pending.resolve(reply({ tenant_id: tenantA, team_name: 'A' }))
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('team')
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(true)
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith('/auth/login'),
      ),
    ).toHaveLength(1)
  })
  it('保存済みbb.authだけではsession通信も/team到達も許さない', async () => {
    const auth = useAuthStore(pinia)
    localStorage.removeItem('bb.auth.intent')
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        sessionId: tenantA,
        teamName: '保存A',
        teamId: tenantA,
      }),
    )
    auth.syncFromStorage()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    expect(router.currentRoute.value.name).toBe('login')
    expect(auth.isAuthenticated).toBe(false)
    expect(auth.teamId).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('旧Aのselfと一覧がBへの切替後に届いても画面/cacheへ採用しない', async () => {
    const auth = useAuthStore(pinia)
    const pendingSelfA = deferred()
    const pendingOpponentsA = deferred()
    let oldSelfHeaders: Headers | undefined
    let oldOpponentsHeaders: Headers | undefined
    fetchMock.mockImplementation(async (url, init) => {
      const headers = new Headers(init?.headers)
      if (headers.get('X-Pitchlog-Expected-Tenant') === tenantA) {
        if (routePath(url) === '/api/team-records/self') {
          oldSelfHeaders = headers
          return pendingSelfA.promise
        }
        oldOpponentsHeaders = headers
        return pendingOpponentsA.promise
      }
      return rosterReply(url, init, tenantB)
    })
    setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'A' })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    expect(oldSelfHeaders).toBeDefined()
    expect(oldOpponentsHeaders).toBeDefined()
    expect(rosterCalls('/api/team-records/self', tenantA)).toHaveLength(1)
    expect(rosterCalls('/api/team-records', tenantA)).toHaveLength(1)
    setVerifiedAuthForTest(auth, { teamId: tenantB, teamName: 'B' })
    await flushPromises()
    pendingSelfA.resolve(
      reply(
        {
          id: '32345678-1234-4234-8234-123456789abc',
          kind: 'self',
          name: '旧A自己応答の固有名',
          hidden_at: null,
        },
        200,
        {
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': oldSelfHeaders!.get(
            'X-Pitchlog-Tenant-Challenge',
          )!,
        },
      ),
    )
    pendingOpponentsA.resolve(
      reply(
        {
          items: [
            {
              id: '42345678-1234-4234-8234-123456789abc',
              kind: 'opponent',
              name: '旧A一覧応答の固有名',
              hidden_at: null,
            },
          ],
          next_cursor: null,
        },
        200,
        {
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': oldOpponentsHeaders!.get(
            'X-Pitchlog-Tenant-Challenge',
          )!,
        },
      ),
    )
    await flushPromises()
    expect(auth.teamId).toBeNull()
    expect(auth.isAuthenticated).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
    const cachedData = JSON.stringify(
      queryClient
        .getQueryCache()
        .getAll()
        .map((q) => q.state.data),
    )
    for (const staleName of ['旧A自己応答の固有名', '旧A一覧応答の固有名']) {
      expect(wrapper.text()).not.toContain(staleName)
      expect(cachedData).not.toContain(staleName)
    }
    expect(rosterCalls('/api/team-records/self', tenantA)).toHaveLength(1)
    expect(rosterCalls('/api/team-records', tenantA)).toHaveLength(1)
  })
  it('providerが異なる場合はsession/tenant通信を開始しない', async () => {
    const foreign = createPinia()
    setActivePinia(foreign)
    try {
      const router = createAppRouter(createMemoryHistory())
      await router.push('/team')
      expect(router.currentRoute.value.name).toBe('login')
      expect(fetchMock).not.toHaveBeenCalled()
    } finally {
      disposePinia(foreign)
      setActivePinia(pinia)
    }
  })
  it.each(['epoch', 'tenant', 'pending'])(
    'C1結果の%s境界をguardで拒否する',
    async (kind) => {
      const auth = useAuthStore(pinia)
      setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'A' })
      const spy = vi.spyOn(authApi, 'ensureSessionVerified')
      if (kind === 'pending')
        spy.mockRejectedValueOnce(new authApi.AuthOperationInProgressError())
      else
        spy.mockResolvedValueOnce({
          status: 'authenticated',
          authEpoch: auth.authEpoch - (kind === 'epoch' ? 1 : 0),
          tenantId: kind === 'tenant' ? tenantB : tenantA,
          teamName: 'A',
        })
      const router = createAppRouter(createMemoryHistory())
      await router.push('/team')
      expect(spy).toHaveBeenCalledOnce()
      expect(router.currentRoute.value.name).toBe('login')
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )
  it('認証変更でも公開トップの局所stateを再生成しない', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    const wrapper = view(router)
    const publicScreen = wrapper.getComponent(StrikeZoneCompareHost).vm.$.uid
    setVerifiedAuthForTest(useAuthStore(pinia), {
      teamId: tenantA,
      teamName: 'A',
    })
    await flushPromises()
    expect(wrapper.getComponent(StrikeZoneCompareHost).vm.$.uid).toBe(
      publicScreen,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('正常なtenant metadataでも不正200のselfを選択とcacheへ採用しない', async () => {
    const auth = useAuthStore(pinia)
    fetchMock.mockImplementation(async (url, init) => {
      const path = routePath(url)
      const headers = new Headers(init?.headers)
      const tenantHeaders = {
        'X-Pitchlog-Tenant-Match': '1',
        'X-Pitchlog-Tenant-Challenge':
          headers.get('X-Pitchlog-Tenant-Challenge') ?? '',
      }
      if (path === '/api/team-records/self')
        return reply(
          {
            id: '32345678-1234-4234-8234-123456789abc',
            kind: 'opponent',
            name: '不正な自チーム候補',
            hidden_at: null,
          },
          200,
          tenantHeaders,
        )
      if (path === '/api/team-records')
        return reply({ items: [], next_cursor: null }, 200, tenantHeaders)
      if (path === '/api/players')
        return reply({ items: [], next_cursor: null }, 200, tenantHeaders)
      throw new Error(`想定外の経路: ${path}`)
    })
    setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'A' })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="self-team-error"]').exists()).toBe(
        true,
      ),
    )

    expect(rosterCalls('/api/team-records/self', tenantA)).toHaveLength(1)
    expect(rosterCalls('/api/team-records', tenantA)).toHaveLength(1)
    expect(auth.isAuthenticated).toBe(true)
    expect(
      queryClient.getQueryData(
        rosterQueryKeys.selfTeamRecord(tenantA, auth.authEpoch),
      ),
    ).toBeUndefined()
    expect(wrapper.text()).not.toContain('不正な自チーム候補')
    expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(
      false,
    )
    expect(wrapper.get('#players-heading').text()).toBe('選手')
    expect(
      fetchMock.mock.calls.filter(([url]) => routePath(url) === '/api/players'),
    ).toHaveLength(0)
  })
  it('tenant-bound401は保護画面を解除して/loginへ移す', async () => {
    const pendingSelf = deferred()
    const pendingOpponents = deferred()
    fetchMock.mockImplementation(async (url) => {
      if (routePath(url) === '/api/team-records/self')
        return pendingSelf.promise
      if (routePath(url) === '/api/team-records')
        return pendingOpponents.promise
      return reply({}, 401)
    })
    setVerifiedAuthForTest(useAuthStore(pinia), {
      teamId: tenantA,
      teamName: 'A',
    })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(true)
    expect(rosterCalls('/api/team-records/self', tenantA)).toHaveLength(1)
    expect(rosterCalls('/api/team-records', tenantA)).toHaveLength(1)
    for (const call of [
      ...rosterCalls('/api/team-records/self', tenantA),
      ...rosterCalls('/api/team-records', tenantA),
    ]) {
      expect(call[1]?.method).toBe('GET')
    }
    const unauthenticated = reply({}, 401)
    expect(unauthenticated.status).toBe(401)
    pendingSelf.resolve(unauthenticated)
    pendingOpponents.resolve(reply({}, 401))
    await flushPromises()
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAuthStore(pinia).isAuthenticated).toBe(false)
    expect(
      fetchMock.mock.calls.every(([, init]) => init?.method === 'GET'),
    ).toBe(true)
    expect(rosterCalls('/api/team-records/self')).toHaveLength(1)
    expect(rosterCalls('/api/team-records')).toHaveLength(1)
  })
  it('別タブのstorage削除で保護画面を解除しtenant通信を再開しない', async () => {
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith('/auth/session')) return reply({}, 503)
      return rosterReply(url, init)
    })
    setVerifiedAuthForTest(useAuthStore(pinia), {
      teamId: tenantA,
      teamName: 'A',
    })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(true)
    expect(rosterCalls('/api/team-records/self', tenantA)).toHaveLength(1)
    expect(rosterCalls('/api/team-records', tenantA)).toHaveLength(1)
    expect(useAuthStore(pinia).teamId).toBe(tenantA)
    localStorage.removeItem('bb.auth.intent')
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'bb.auth.intent',
        newValue: null,
        storageArea: localStorage,
      }),
    )
    await flushPromises()
    expect(wrapper.findComponent(TeamScreen).exists()).toBe(false)
    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.text()).toContain('認証')
    expect(rosterCalls('/api/team-records/self')).toHaveLength(1)
    expect(rosterCalls('/api/team-records')).toHaveLength(1)
  })
  it('hydration待ちの後でもprovider不一致なら通信しない', async () => {
    const auth = useAuthStore(pinia)
    auth.hasHydrated = false
    const foreign = createPinia()
    const router = createAppRouter(createMemoryHistory())
    const navigating = router.push('/team')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    try {
      setActivePinia(foreign)
      auth.hasHydrated = true
      await navigating
      expect(router.currentRoute.value.name).toBe('login')
      expect(fetchMock).not.toHaveBeenCalled()
    } finally {
      auth.hasHydrated = true
      disposePinia(foreign)
      setActivePinia(pinia)
    }
  })
})

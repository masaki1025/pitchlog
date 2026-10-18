import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import type { Plugin } from 'vue'
import { createMemoryHistory, createWebHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import { installAppProviders, pinia } from './appProviders'
import { queryClient } from './lib/queryClient'
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
  useAuthStore(pinia).signOut()
  queryClient.clear()
  fetchMock.mockReset().mockImplementation(async () => reply({}, 401))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  useAuthStore(pinia).signOut()
  queryClient.clear()
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
    fetchMock.mockImplementation(async (_url, init) => {
      const headers = new Headers(init?.headers)
      return reply({ items: [], next_cursor: null }, 200, {
        'X-Pitchlog-Tenant-Match': '1',
        'X-Pitchlog-Tenant-Challenge':
          headers.get('X-Pitchlog-Tenant-Challenge') ?? '',
      })
    })
    const auth = useAuthStore(pinia)
    auth.signIn({ teamId: tenantA, teamName: 'A' })
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    const wrapper = view(router)
    await flushPromises()
    const oldScreen = wrapper.getComponent(TeamScreen).vm
    queryClient.setQueryData(['old-tenant-marker'], '旧A')
    auth.signIn({ teamId: tenantB, teamName: 'B' })
    await flushPromises()
    expect(wrapper.getComponent(TeamScreen).vm).not.toBe(oldScreen)
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
          return reply({ status: 'authenticated' })
        if (String(url).endsWith('/auth/session'))
          return reply({ tenant_id: tenantA, team_name: 'A' })
        const headers = new Headers(init?.headers)
        return reply({ items: [], next_cursor: null }, 200, {
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge':
            headers.get('X-Pitchlog-Tenant-Challenge') ?? '',
        })
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
        return reply({ status: 'authenticated' })
      if (String(url).endsWith('/auth/session')) return pending.promise
      const headers = new Headers(init?.headers)
      return reply({ items: [], next_cursor: null }, 200, {
        'X-Pitchlog-Tenant-Match': '1',
        'X-Pitchlog-Tenant-Challenge':
          headers.get('X-Pitchlog-Tenant-Challenge') ?? '',
      })
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
  it('保存済みbb.authがあってもsession確認前の/team到達を許さない', async () => {
    const auth = useAuthStore(pinia)
    auth.signIn({ teamId: tenantA, teamName: '保存A' })
    const saved = localStorage.getItem(AUTH_STORAGE_KEY)!
    auth.signOut()
    localStorage.setItem(AUTH_STORAGE_KEY, saved)
    auth.syncFromStorage()
    const pending = deferred()
    fetchMock.mockReturnValueOnce(pending.promise)
    const router = createAppRouter(createMemoryHistory())
    const navigating = router.push('/team')
    await flushPromises()
    expect(auth.isAuthenticated).toBe(false)
    expect(router.currentRoute.value.name).not.toBe('team')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    pending.resolve(reply({}, 401))
    await navigating
    expect(router.currentRoute.value.name).toBe('login')
    expect(auth.teamId).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

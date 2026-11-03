import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import type { PreparingGameCreate } from '../api/games'
import { installAppProviders, pinia } from '../appProviders'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import { usePreparingCreateProvider } from './GameScreenPreparingCreateProvider'

const tenant = '11111111-1111-4111-8111-111111111111'
const otherTenant = '21111111-1111-4111-8111-111111111111'
const self = '31111111-1111-4111-8111-111111111111'
const opponent = '41111111-1111-4111-8111-111111111111'
const gameId = '51111111-1111-4111-8111-111111111111'
const options = {
  game_types: [
    'game_official',
    'game_semi_official',
    'game_open',
    'game_intrasquad',
    'game_other',
  ].map((key) => ({ key, display_name: key })),
  tournaments: {
    items: [{ key: 'opaque', display_name: '大会' }],
    next_cursor: 'option-next' as string | null,
  },
}
const payload: PreparingGameCreate = {
  scheduled_at: '2026-10-24T10:00:00+09:00',
  game_type_key: 'game_open',
  away_team_record_id: self,
  home_team_record_id: opponent,
  tournament: { kind: 'new', display_name: ' 大会　' },
  plate_umpire: '<b>主審</b>',
  section_label: '節',
  week_label: '',
  day_label: null,
  game_number_label: '1',
}
// UI配線用のtransport fixture。正規計算/実DB保存成功を証明しない。
const game = {
  id: gameId,
  ...payload,
  tournament_key: 'new-opaque',
  status: 'preparing',
  applied_rules: { ui_fixture: true },
}
const fetchMock = vi.fn<typeof fetch>()
let wrapper: VueWrapper | undefined
let provider: ReturnType<typeof usePreparingCreateProvider>
let router: Router
function response(body: unknown, init?: RequestInit, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Pitchlog-Tenant-Match': '1',
      'X-Pitchlog-Tenant-Challenge':
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge') ?? '',
    },
  })
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function normal(url: RequestInfo | URL, init?: RequestInit): Response {
  const path = String(url)
  if (path.includes('/games/preparation-options'))
    return response(options, init)
  if (path.includes('/team-records/self'))
    return response(
      { id: self, kind: 'self', name: '自分', hidden_at: null },
      init,
    )
  if (path.includes('/team-records?'))
    return response(
      {
        items: [
          { id: opponent, kind: 'opponent', name: '相手', hidden_at: null },
        ],
        next_cursor: 'team-next',
      },
      init,
    )
  return response(game, init, init?.method === 'POST' ? 201 : 200)
}
async function start() {
  const Probe = defineComponent({
    setup() {
      provider = usePreparingCreateProvider()
      return () => h('div', provider.status.value)
    },
  })
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/games', component: Probe },
      {
        path: '/games/:id/record',
        component: Probe,
      },
    ],
  })
  await router.push('/games')
  wrapper = mount(Probe, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  await flushPromises()
}
const posts = () =>
  fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')
beforeEach(() => {
  localStorage.clear()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    onLine: true,
    locks: {
      request: vi.fn(async (_name, _options, action) =>
        action({ name: 'create-unit' }),
      ),
    },
  })
  setVerifiedAuthForTest(useAuthStore(pinia), { teamId: tenant, teamName: 'A' })
  queryClient.clear()
  fetchMock
    .mockReset()
    .mockImplementation(async (url, init) => normal(url, init))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  useAuthStore(pinia).signOut()
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('GET3供給後もPOSTは明示操作だけ、送信中の二重呼出しを即時遮断する', async () => {
  await start()
  expect(provider.status.value).toBe('ready')
  expect(fetchMock).toHaveBeenCalledTimes(3)
  expect(posts()).toHaveLength(0)
  const pending = deferred<Response>()
  let postInit: RequestInit | undefined
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'POST') {
      postInit = init
      return pending.promise
    }
    return normal(url, init)
  })
  const sending = provider.submit(payload)
  void provider.submit(payload)
  expect(provider.status.value).toBe('sending')
  await flushPromises()
  expect(posts()).toHaveLength(1)
  expect(JSON.parse(String(posts()[0]?.[1]?.body))).toEqual(payload)
  pending.resolve(response(game, postInit, 201))
  await sending
  expect(provider.status.value).toBe('created')
  expect(router.currentRoute.value.path).toBe('/games')
  const before = fetchMock.mock.calls.length
  await provider.confirmCreated()
  await flushPromises()
  expect(fetchMock.mock.calls.slice(before).map(([url]) => url)).toEqual([
    `/api/games/${gameId}`,
  ])
  expect(router.currentRoute.value.path).toBe(`/games/${gameId}/record`)
  expect(posts()).toHaveLength(1)
})
it('応答消失は通常clientが認証を未確認に戻し、focus/onlineでPOSTを再送しない', async () => {
  await start()
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'POST') throw new TypeError('通信中断')
    return normal(url, init)
  })
  await provider.submit(payload)
  expect(useAuthStore(pinia).isAuthenticated).toBe(false)
  expect(provider.choices.value).toBeNull()
  expect(provider.created.value).toBeNull()
  window.dispatchEvent(new Event('focus'))
  window.dispatchEvent(new Event('online'))
  await provider.submit(payload)
  await provider.load()
  await flushPromises()
  expect(posts()).toHaveLength(1)
})
it('offlineはPOST0、認証切替後の遅延POST/GETを旧tenantの結果として破棄する', async () => {
  await start()
  provider.online.value = false
  await provider.submit(payload)
  expect(posts()).toHaveLength(0)
  provider.online.value = true
  const pending = deferred<Response>()
  let postInit: RequestInit | undefined
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'POST') {
      postInit = init
      return pending.promise
    }
    return normal(url, init)
  })
  const sending = provider.submit(payload)
  await flushPromises()
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: otherTenant,
    teamName: 'B',
  })
  expect(provider.created.value).toBeNull()
  expect(provider.choices.value).toBeNull()
  pending.resolve(response(game, postInit, 201))
  await sending
  await flushPromises()
  expect(provider.created.value).toBeNull()
  expect(router.currentRoute.value.path).toBe('/games')
  expect(posts()).toHaveLength(1)
})
it('破棄済みproviderはlate POSTでcache/成功表示/経路を変えない', async () => {
  await start()
  const pending = deferred<Response>()
  let postInit: RequestInit | undefined
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === 'POST') {
      postInit = init
      return pending.promise
    }
    return normal(url, init)
  })
  const sending = provider.submit(payload)
  await flushPromises()
  wrapper?.unmount()
  wrapper = undefined
  const unmountedPath = router.currentRoute.value.path
  pending.resolve(response(game, postInit, 201))
  await sending
  expect(provider.created.value).toBeNull()
  expect(router.currentRoute.value.path).toBe(unmountedPath)
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
})
it('大会/相手の不透明cursorを別々に送り、全件収集や自動先読みをしない', async () => {
  await start()
  provider.page('options', 'next')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-3)?.[0]).toBe(
    '/api/games/preparation-options?limit=20&cursor=option-next',
  )
  provider.page('teams', 'next')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-1)?.[0]).toBe(
    '/api/team-records?limit=20&cursor=team-next',
  )
  provider.page('options', 'previous')
  await flushPromises()
  expect(fetchMock.mock.calls.at(-3)?.[0]).toBe(
    '/api/games/preparation-options?limit=20',
  )
  expect(posts()).toHaveLength(0)
})
it('同IDの確認GETが失敗してもPOSTせず、同じIDへの明示GETだけ再試行する', async () => {
  await start()
  await provider.submit(payload)
  let fail = true
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url) === `/api/games/${gameId}` && fail) {
      fail = false
      return response({}, init, 503)
    }
    return normal(url, init)
  })
  await provider.confirmCreated()
  expect(provider.status.value).toBe('created')
  expect(router.currentRoute.value.path).toBe('/games')
  await provider.confirmCreated()
  await flushPromises()
  expect(router.currentRoute.value.path).toBe(`/games/${gameId}/record`)
  expect(posts()).toHaveLength(1)
})

it('503はunknownで止まり、明示load/submitでも同じPOSTを再送しない', async () => {
  await start()
  fetchMock.mockImplementation(async (url, init) =>
    init?.method === 'POST' ? response({}, init, 503) : normal(url, init),
  )
  await provider.submit(payload)
  expect(provider.status.value).toBe('unknown')
  expect(provider.created.value).toBeNull()
  await provider.load()
  await provider.submit(payload)
  await flushPromises()
  expect(posts()).toHaveLength(1)
})
it('作成結果の明示GET中に経路が変われば、旧gameの経路へ戻さない', async () => {
  await start()
  await provider.submit(payload)
  const pending = deferred<Response>()
  let getInit: RequestInit | undefined
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url) === `/api/games/${gameId}`) {
      getInit = init
      return pending.promise
    }
    return normal(url, init)
  })
  const confirming = provider.confirmCreated()
  await flushPromises()
  await router.push(`/games/${opponent}/record`)
  pending.resolve(response(game, getInit))
  await confirming
  await flushPromises()
  expect(router.currentRoute.value.path).toBe(`/games/${opponent}/record`)
  expect(provider.created.value).toBeNull()
  expect(posts()).toHaveLength(1)
})

it('既存名409等の確定拒否は入力修正へ戻し、明示操作なしでPOSTしない', async () => {
  await start()
  fetchMock.mockImplementation(async (url, init) =>
    init?.method === 'POST' ? response({}, init, 409) : normal(url, init),
  )
  await provider.submit(payload)
  expect(provider.status.value).toBe('ready')
  expect(provider.created.value).toBeNull()
  expect(provider.message.value).toContain('入力と大会の選択')
  window.dispatchEvent(new Event('focus'))
  await flushPromises()
  expect(posts()).toHaveLength(1)
})

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setActivePinia } from 'pinia'
import App from '../App.vue'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { installAppProviders, pinia } from '../appProviders'
import { queryClient } from '../lib/queryClient'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import GameScreen from './GameScreen.vue'
import GameScreenEntryHost from './GameScreenEntryHost.vue'
import GameScreenEntryRecordHost from './GameScreenEntryRecordHost.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
const tenant = '12345678-1234-4234-8234-123456789abc'
const other = '22345678-1234-4234-8234-123456789abc'
const id = '32345678-1234-4234-8234-123456789abc'
const id2 = '42345678-1234-4234-8234-123456789abc'
const game = {
  id,
  scheduled_at: '2026-10-24T10:00:00+09:00',
  game_type_key: 'game_open',
  tournament_key: '保存大会',
  away_team_record_id: other,
  home_team_record_id: tenant,
  plate_umpire: '<img src=x onerror=alert(1)>',
  section_label: '<b>保存ラベル</b>',
  week_label: null,
  day_label: null,
  game_number_label: null,
  status: 'preparing',
  applied_rules: {
    regulationInnings: 9,
    dh: true,
    value: '<svg onload=alert(1)>',
  },
}
const wrappers: VueWrapper[] = []
const fetchMock = vi.fn<typeof fetch>()
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
async function view(path = '/games') {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const wrapper = mount(App, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}
function button(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find((b) => b.text() === text)!
}
function providerProbe(
  capture: (value: ReturnType<typeof usePreparingEntryProvider>) => void,
) {
  return defineComponent({
    setup() {
      const value = usePreparingEntryProvider('list')
      capture(value)
      return () =>
        h(
          'div',
          value.page.value?.data?.items[0]?.label ?? value.page.value?.status,
        )
    },
  })
}
function assertClosed(wrapper: VueWrapper) {
  expect(wrapper.findComponent(GameScreen).exists()).toBe(false)
  expect(wrapper.find('input').exists()).toBe(false)
  expect(wrapper.find('select').exists()).toBe(false)
  for (const b of wrapper
    .findAll('button')
    .filter((b) => /再開|開始|保存|送信/.test(b.text())))
    expect(b.attributes('disabled')).toBeDefined()
}
beforeEach(() => {
  localStorage.clear()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    locks: {
      request: vi.fn(async (_n, _o, action) =>
        action({ name: 'provider-unit' }),
      ),
    },
  })
  setVerifiedAuthForTest(useAuthStore(pinia), { teamId: tenant, teamName: 'A' })
  queryClient.clear()
  fetchMock
    .mockReset()
    .mockImplementation(async (url, init) =>
      response(
        String(url).startsWith('/api/games?')
          ? { items: [game], next_cursor: null }
          : game,
        init,
      ),
    )
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  useAuthStore(pinia).signOut()
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('実route hostからGET一覧/詳細へ接続し、保存値をtext表示して全書込を閉じる', async () => {
  const { wrapper, router } = await view()
  expect(wrapper.findComponent(GameScreenEntryHost).exists()).toBe(true)
  expect(wrapper.get('h1').text()).toBe('準備中の試合')
  expect(wrapper.text()).toContain('<b>保存ラベル</b>')
  expect(wrapper.find('b').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('開始候補')
  assertClosed(wrapper)
  await wrapper.get('a[href$="/record"]').trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.path).toBe(`/games/${id}/record`)
  expect(wrapper.findComponent(GameScreenEntryRecordHost).exists()).toBe(true)
  expect(wrapper.text()).toContain('保存された適用規則')
  expect(wrapper.text()).toContain('"regulationInnings": 9')
  expect(wrapper.text()).toContain('<svg onload=alert(1)>')
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  expect(wrapper.text()).toContain('スタメン・記録権・下書き復元：未取得')
  expect(wrapper.find('svg').exists()).toBe(false)
  expect(wrapper.find('img').exists()).toBe(false)
  assertClosed(wrapper)
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    '/api/games?limit=20',
    `/api/games/${id}`,
  ])
  expect(fetchMock.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(
    true,
  )
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
})
it('不透明cursorの実履歴を往復し、初期nullへ戻る・失敗同page retry・二重操作を検査する', async () => {
  let fail = true
  const pending = deferred<Response>()
  let pendingInit: RequestInit | undefined
  fetchMock.mockImplementation(async (url, init) => {
    if (String(url).includes('cursor=opaque')) {
      if (fail) {
        fail = false
        return response({}, init, 503)
      }
      pendingInit = init
      return pending.promise
    }
    return response({ items: [game], next_cursor: 'opaque' }, init)
  })
  const { wrapper } = await view()
  await button(wrapper, '次のページ').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('読み取れません')
  await button(wrapper, 'このページを再試行').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('確認中')
  expect(fetchMock).toHaveBeenCalledTimes(3)
  pending.resolve(
    response(
      {
        items: [{ ...game, id: id2, section_label: '次頁' }],
        next_cursor: null,
      },
      pendingInit,
    ),
  )
  await flushPromises()
  expect(wrapper.text()).toContain('2ページ目')
  expect(wrapper.text()).not.toContain('<b>保存ラベル</b>')
  await button(wrapper, '前のページ').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('1ページ目')
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    '/api/games?limit=20',
    '/api/games?limit=20&cursor=opaque',
    '/api/games?limit=20&cursor=opaque',
    '/api/games?limit=20',
  ])
})
it.each([404, 403, 503, 200])(
  '詳細%sをdenied/failedへ閉じ、明示retryだけ行う',
  async (status) => {
    fetchMock.mockImplementation(async (_url, init) =>
      response({}, init, status),
    )
    const { wrapper } = await view(`/games/${id}/record`)
    expect(wrapper.text()).toContain(
      status === 404 || status === 403
        ? 'この試合の情報を確認できません'
        : '読み取れません',
    )
    assertClosed(wrapper)
    // 記録画面は詳細の拒否後にサーバーの開始済み/記録済み状態も確認する。
    const detailCalls = () =>
      fetchMock.mock.calls.filter(([url]) => String(url) === `/api/games/${id}`)
        .length
    expect(detailCalls()).toBe(1)
    fetchMock.mockImplementation(async (_url, init) => response(game, init))
    await button(wrapper, 'この試合を再試行').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('保存大会')
    assertClosed(wrapper)
    expect(detailCalls()).toBe(2)
  },
)
it('不正UUIDをfetch前に閉じる', async () => {
  const { wrapper } = await view('/games/not-a-uuid/record')
  expect(wrapper.text()).toContain('試合IDが正しくありません')
  expect(fetchMock).not.toHaveBeenCalled()
  assertClosed(wrapper)
})
it('401は認証を失効しloginへ戻る', async () => {
  fetchMock.mockImplementation(async (_url, init) => response({}, init, 401))
  const { wrapper, router } = await view(`/games/${id}/record`)
  expect(router.currentRoute.value.name).toBe('login')
  expect(wrapper.findComponent(GameScreenEntryRecordHost).exists()).toBe(false)
  expect(useAuthStore(pinia).isAuthenticated).toBe(false)
})
it.each(['tenant', 'epoch', 'path', 'unmount'])(
  '遅延headersは%s変更後に表示/cacheへ採らず、Cookie不確実性も維持する',
  async (kind) => {
    const pending = deferred<Response>()
    let oldInit: RequestInit | undefined
    fetchMock.mockImplementation((_url, init) => {
      oldInit = init
      return pending.promise
    })
    const { wrapper, router } = await view(`/games/${id}/record`)
    const signal = oldInit?.signal
    if (kind === 'tenant')
      setVerifiedAuthForTest(useAuthStore(pinia), {
        teamId: other,
        teamName: 'B',
      })
    else if (kind === 'epoch') useAuthStore(pinia).signOut()
    else if (kind === 'path') await router.push('/help')
    else wrapper.unmount()
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    pending.resolve(
      response({ ...game, tournament_key: '旧応答固有値' }, oldInit),
    )
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧応答固有値')
    expect(
      JSON.stringify(
        queryClient
          .getQueryCache()
          .getAll()
          .map((q) => q.state.data),
      ),
    ).not.toContain('旧応答固有値')
  },
)
it('本文待ち中の失効後に内容を採用しない', async () => {
  const body = deferred<string>()
  let read = false
  fetchMock.mockImplementation(async (_url, init) => {
    const res = response(game, init)
    vi.spyOn(res, 'text').mockImplementation(() => {
      read = true
      return body.promise
    })
    return res
  })
  const { wrapper } = await view(`/games/${id}/record`)
  expect(read).toBe(true)
  useAuthStore(pinia).signOut()
  body.resolve(JSON.stringify({ ...game, tournament_key: '本文旧値' }))
  await flushPromises()
  expect(wrapper.text()).not.toContain('本文旧値')
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
})
it('A→B→Aと非協調abortでも内部要求世代で旧Aを拒否する', async () => {
  const pending = deferred<Response>()
  let oldInit: RequestInit | undefined
  let count = 0
  fetchMock.mockImplementation(async (_url, init) => {
    count += 1
    if (count === 1) {
      oldInit = init
      return pending.promise
    }
    return response({ items: [game], next_cursor: null }, init)
  })
  const router = createAppRouter(createMemoryHistory())
  await router.push('/games')
  const probe = providerProbe(() => {})
  const wrapper = mount(probe, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  // 経路を変えたあと同じpathへ戻しても旧要求世代を再利用しない。
  await router.push('/help')
  await router.push('/games')
  await flushPromises()
  expect(oldInit?.signal?.aborted).toBe(true)
  pending.resolve(
    response(
      { items: [{ ...game, section_label: '旧A応答' }], next_cursor: null },
      oldInit,
    ),
  )
  await flushPromises()
  expect(wrapper.text()).not.toContain('旧A応答')
  expect(queryClient.getQueryCache().getAll()).toHaveLength(0)
})

it('同じ詳細hostのID変更と壊れた応答で旧readyを代替表示しない', async () => {
  const { wrapper, router } = await view(`/games/${id}/record`)
  expect(wrapper.text()).toContain('保存大会')
  fetchMock.mockImplementation(async (_url, init) =>
    response({ ...game, id: id2, status: 'finished' }, init),
  )
  await router.push(`/games/${id2}/record`)
  await flushPromises()
  expect(wrapper.text()).toContain('読み取れません')
  expect(wrapper.text()).not.toContain('保存大会')
  expect(wrapper.text()).not.toContain('<b>保存ラベル</b>')
  assertClosed(wrapper)
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    `/api/games/${id}`,
    `/api/games/${id2}`,
  ])
})

it('未訪問cursorと送信中の二重要求を拒否し、失敗から実訪問pageへ戻れる', async () => {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/games')
  let controls!: ReturnType<typeof usePreparingEntryProvider>
  const probe = providerProbe((value) => {
    controls = value
  })
  const wrapper = mount(probe, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  const pending = deferred<Response>()
  let init: RequestInit | undefined
  await flushPromises()
  controls.requestPage('invented')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  fetchMock.mockImplementation((_url, received) => {
    init = received
    return pending.promise
  })
  // 次cursorがないpageからは架空の次ページを作らない。
  controls.requestPage('unvisited')
  expect(fetchMock).toHaveBeenCalledTimes(1)
  controls.retry()
  controls.retry()
  controls.requestPage(null)
  expect(fetchMock).toHaveBeenCalledTimes(2)
  pending.resolve(response({}, init, 503))
  await flushPromises()
  expect(controls.page.value?.status).toBe('failed')
  expect(controls.page.value?.data).toBeUndefined()
  fetchMock.mockImplementation(async (_url, received) =>
    response({ items: [], next_cursor: null }, received),
  )
  controls.requestPage(null)
  await flushPromises()
  expect(controls.page.value?.data?.pageLabel).toBe('1ページ目')
  expect(controls.page.value?.data?.canPrevious).toBe(false)
})

it('一覧の失敗pageから直前のnullページへ戻り、履歴に失敗を加えない', async () => {
  fetchMock.mockImplementation(async (url, init) =>
    String(url).includes('cursor=')
      ? response({}, init, 503)
      : response({ items: [game], next_cursor: 'opaque' }, init),
  )
  const { wrapper } = await view()
  const next = button(wrapper, '次のページ')
  await Promise.all([next.trigger('click'), next.trigger('click')])
  await flushPromises()
  expect(fetchMock).toHaveBeenCalledTimes(2)
  await button(wrapper, '直前のページに戻る').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('1ページ目')
  expect(button(wrapper, '前のページ').attributes('disabled')).toBeDefined()
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    '/api/games?limit=20',
    '/api/games?limit=20&cursor=opaque',
    '/api/games?limit=20',
  ])
})

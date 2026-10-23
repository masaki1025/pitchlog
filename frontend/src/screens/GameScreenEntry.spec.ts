import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '../App.vue'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { installAppProviders, pinia } from '../appProviders'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import GameScreen from './GameScreen.vue'
import GameScreenEntry from './GameScreenEntry.vue'
import { resolveGameEntryReturnPath } from './GameScreenEntryNavigation'
import GameScreenEntryRecord from './GameScreenEntryRecord.vue'
import {
  existingStateLabel,
  type EntryEnvironment,
  type EntrySupply,
  type GameListPage,
  type RecordDetail,
  type StartCandidate,
} from './GameScreenEntryTypes'

const tenantA = '12345678-1234-4234-8234-123456789abc'
const tenantB = '22345678-1234-4234-8234-123456789abc'
const gameId = '32345678-1234-4234-8234-123456789abc'
const gameId2 = '42345678-1234-4234-8234-123456789abc'
const fetchMock = vi.fn<typeof fetch>()
const wrappers: VueWrapper[] = []
const provider = { install: installAppProviders }
const environment: EntryEnvironment = {
  premises: { 1: 'met', 5: 'met', 6: 'met' },
  persistence: 'granted',
  connectivity: 'online',
  queuedCount: 4,
}
const candidate: StartCandidate = {
  gameId,
  tenantId: tenantA,
  label: '筑波大学対東京大学',
  lineup: { status: 'ready', value: 'スタメン確定' },
  rules: { status: 'ready', value: '九回制' },
  recordingRight: 'held',
  existingState: 'draft',
}

function supply<T>(
  path: string,
  data: T,
  requestKey: string | null = null,
): EntrySupply<T> {
  return {
    tenantId: tenantA,
    authEpoch: useAuthStore(pinia).authEpoch,
    path,
    requestKey,
    status: 'ready',
    data,
  }
}

function page(
  items = [{ gameId, tenantId: tenantA, label: '試合A', stateLabel: '中断中' }],
): GameListPage {
  return { items, pageLabel: '1ページ目', previousKey: null, nextKey: 'next' }
}

async function mountedEntry(
  props: InstanceType<typeof GameScreenEntry>['$props'] = {},
) {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/games')
  const wrapper = mount(GameScreenEntry, {
    props,
    global: { plugins: [provider, router] },
  })
  wrappers.push(wrapper)
  return { wrapper, router }
}

async function mountedRecord(
  path: string,
  props: InstanceType<typeof GameScreenEntryRecord>['$props'] = {},
) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const wrapper = mount(GameScreenEntryRecord, {
    props,
    global: { plugins: [provider, router] },
  })
  wrappers.push(wrapper)
  return { wrapper, router }
}

beforeEach(() => {
  localStorage.clear()
  vi.stubGlobal('navigator', {
    locks: {
      request: vi.fn(async (_name, _options, callback) =>
        callback({ name: 'entry-fixture' }),
      ),
    },
  })
  fetchMock.mockReset().mockResolvedValue(new Response('{}', { status: 401 }))
  vi.stubGlobal('fetch', fetchMock)
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: tenantA,
    teamName: 'A',
  })
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  useAuthStore(pinia).signOut()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('登録済みrouteと認証境界', () => {
  it('製品routeは準備中readだけを供給し、記録入力は開かない', async () => {
    fetchMock.mockImplementation(
      async (url, init) =>
        new Response(
          JSON.stringify(
            String(url).includes('?') ? { items: [], next_cursor: null } : {},
          ),
          {
            headers: {
              'Content-Type': 'application/json',
              'X-Pitchlog-Tenant-Match': '1',
              'X-Pitchlog-Tenant-Challenge':
                new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge') ??
                '',
            },
          },
        ),
    )
    const router = createAppRouter(createMemoryHistory())
    await router.push('/games')
    const wrapper = mount(App, { global: { plugins: [provider, router] } })
    wrappers.push(wrapper)
    await flushPromises()
    expect(wrapper.text()).toContain('準備中の試合')
    expect(wrapper.text()).toContain('このページに試合はありません。')
    await router.push(`/games/${gameId}/record`)
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('game-record')
    expect(wrapper.text()).toContain('準備中試合の保存情報：読み取れません')
    expect(wrapper.text()).toContain('スタメン・記録権・下書き復元：未取得')
    expect(wrapper.findComponent(GameScreen).exists()).toBe(false)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/games?limit=20',
      `/api/games/${gameId}`,
    ])
  })

  it.each(['/games', `/games/${gameId}/record`])(
    '未確認の%sを/loginへ戻し、保護画面を描画しない',
    async (path) => {
      const auth = useAuthStore(pinia)
      auth.signOut()
      const router = createAppRouter(createMemoryHistory())
      await router.push(path)
      const wrapper = mount(App, { global: { plugins: [provider, router] } })
      wrappers.push(wrapper)
      expect(router.currentRoute.value.name).toBe('login')
      expect(router.currentRoute.value.query.redirect).toBe(path)
      expect(wrapper.text()).not.toContain('記録画面の入口')
      expect(
        fetchMock.mock.calls.every(([url]) => url === '/api/auth/session'),
      ).toBe(true)
    },
  )

  it.each([
    ['/games?next=x', '/team'],
    [`/games/${gameId}/record#part`, '/team'],
    ['/games/not-a-uuid/record', '/team'],
    ['/team', '/team'],
  ])('認証前の%sは安全な戻り先%sだけを保持する', async (path, expected) => {
    useAuthStore(pinia).signOut()
    const router = createAppRouter(createMemoryHistory())
    await router.push(path)
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe(expected)
  })

  it.each([
    'https://outside.invalid/games',
    '//outside.invalid',
    '/games//record',
    '/games?x=1',
    '/games#part',
    `/games/${gameId.toUpperCase()}/record`,
    '/games/not-a-uuid/record',
  ])('不正な戻り先%sは/teamへ倒す', (path) => {
    expect(resolveGameEntryReturnPath(path)).toBe('/team')
  })

  it('非tenant/認証世代変更/再検証失敗を取得済み表示に採用しない', async () => {
    const { wrapper } = await mountedEntry({
      page: supply('/games', page()),
      environment: supply('/games', environment),
    })
    expect(wrapper.text()).toContain('試合A')
    expect(wrapper.text()).toContain('未送信件数：4')
    await wrapper.setProps({
      page: { ...supply('/games', page()), tenantId: tenantB },
    })
    expect(wrapper.text()).toContain('試合一覧：未取得')
    await wrapper.setProps({ page: supply('/games', page()) })
    useAuthStore(pinia).beginSessionVerification()
    await flushPromises()
    expect(wrapper.text()).toContain('試合一覧：未取得')
    expect(wrapper.text()).not.toContain('試合A')
    expect(wrapper.text()).toContain('未送信件数：未取得')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['/games', `/games/${gameId}/record`])(
    '%sの再検証失敗・異tenant応答・待機中の世代変更を拒否する',
    async (path) => {
      for (const response of [
        new Response('{}', { status: 500 }),
        new Response(JSON.stringify({ tenant_id: tenantB, team_name: 'B' }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      ]) {
        const auth = useAuthStore(pinia)
        auth.beginSessionVerification()
        fetchMock.mockResolvedValueOnce(response)
        const router = createAppRouter(createMemoryHistory())
        await router.push(path)
        expect(router.currentRoute.value.name).toBe('login')
        expect(auth.isAuthenticated).toBe(false)
        setVerifiedAuthForTest(auth, { teamId: tenantA, teamName: 'A' })
      }

      const auth = useAuthStore(pinia)
      auth.beginSessionVerification()
      let finish!: (response: Response) => void
      fetchMock.mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve
          }),
      )
      const router = createAppRouter(createMemoryHistory())
      const navigating = router.push(path)
      await flushPromises()
      auth.signOut()
      finish(
        new Response(JSON.stringify({ tenant_id: tenantA, team_name: 'A' }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      await navigating
      expect(router.currentRoute.value.name).toBe('login')
      expect(auth.isAuthenticated).toBe(false)
    },
  )
})

describe('一覧・開始・再開の隔離表示', () => {
  it('提供された1ページだけを描画し、前後ページ状態と旧応答を分ける', async () => {
    const { wrapper } = await mountedEntry({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
      environment: supply('/games', environment),
    })
    expect(wrapper.text()).toContain('試合A')
    expect(wrapper.text()).not.toContain('試合B')
    expect(wrapper.get('a').attributes('href')).toBe(`/games/${gameId}/record`)
    const reopen = wrapper
      .findAll('button')
      .find((button) => button.text().includes('再開（未提供）'))!
    reopen.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.find('button:disabled').exists()).toBe(true)
    const previous = wrapper.get('nav button:first-child')
    expect(previous.attributes('disabled')).toBeDefined()
    await wrapper.get('nav button:last-child').trigger('click')
    expect(wrapper.emitted('page-request')?.[0]).toEqual(['next'])
    expect(wrapper.text()).toContain('試合一覧：確認中')
    await wrapper.setProps({ page: supply('/games', page(), null) })
    expect(wrapper.text()).not.toContain('試合A')
    await wrapper.setProps({
      page: supply(
        '/games',
        {
          items: [
            {
              gameId: gameId2,
              tenantId: tenantA,
              label: '試合B',
              stateLabel: '進行中',
            },
          ],
          pageLabel: '2ページ目',
          previousKey: 'previous',
          nextKey: null,
        },
        'next',
      ),
    })
    expect(wrapper.text()).toContain('試合B')
    expect(wrapper.text()).not.toContain('試合A')
    expect(
      wrapper.get('nav button:last-child').attributes('disabled'),
    ).toBeDefined()
    await wrapper.get('nav button:first-child').trigger('click')
    expect(wrapper.emitted('page-request')?.[1]).toEqual(['previous'])
    expect(wrapper.text()).toContain('試合一覧：確認中')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['failed', 'denied'] as const)(
    '%sのページ要求を明示再試行・直前のページへ戻せるが通信はしない',
    async (status) => {
      const { wrapper } = await mountedEntry({ page: supply('/games', page()) })
      await wrapper.get('nav button:last-child').trigger('click')
      expect(wrapper.text()).toContain('試合一覧：確認中')
      expect(wrapper.text()).not.toContain('試合A')
      expect(wrapper.find('nav').exists()).toBe(false)
      await wrapper.setProps({
        page: { ...supply('/games', page(), 'next'), status },
      })
      expect(wrapper.text()).toContain(
        status === 'failed'
          ? '試合一覧：読み取れません'
          : '試合一覧：このページを確認できません',
      )
      expect(wrapper.text()).not.toContain('試合A')
      const retry = wrapper
        .findAll('button')
        .find((button) => button.text() === 'このページを再試行')!
      const back = wrapper
        .findAll('button')
        .find((button) => button.text() === '直前のページに戻る')!
      await retry.trigger('click')
      expect(wrapper.emitted('page-request')?.at(-1)).toEqual(['next'])
      expect(wrapper.text()).toContain('試合一覧：確認中')
      expect(wrapper.text()).not.toContain('試合A')
      await wrapper.setProps({
        page: { ...supply('/games', page(), 'next'), status },
      })
      await back.trigger('click')
      expect(wrapper.emitted('page-request')?.at(-1)).toEqual([null])
      expect(wrapper.text()).toContain('試合一覧：確認中')
      await wrapper.setProps({ page: supply('/games', page()) })
      expect(wrapper.text()).toContain('試合A')
      expect(wrapper.text()).not.toContain('直前のページに戻る')
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it.each(['failed', 'denied'] as const)(
    '初期ページ%sは未取得と区別して再試行し、他scopeの応答は表示しない',
    async (status) => {
      const { wrapper } = await mountedEntry({
        page: { ...supply('/games', page()), status },
      })
      expect(wrapper.text()).not.toContain('試合一覧：未取得')
      expect(wrapper.text()).toContain('このページを再試行')
      expect(wrapper.text()).not.toContain('直前のページに戻る')
      await wrapper
        .findAll('button')
        .find((button) => button.text() === 'このページを再試行')!
        .trigger('click')
      expect(wrapper.emitted('page-request')?.at(-1)).toEqual([null])
      expect(wrapper.text()).toContain('試合一覧：確認中')
      const auth = useAuthStore(pinia)
      setVerifiedAuthForTest(auth, { teamId: tenantB, teamName: 'B' })
      await flushPromises()
      expect(wrapper.text()).toContain('試合一覧：未取得')
      expect(wrapper.text()).not.toContain('このページを再試行')
      expect(wrapper.text()).not.toContain('試合A')
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it('供給された一覧の閲覧リンクは登録済み記録routeへ遷移する', async () => {
    const { wrapper, router } = await mountedEntry({
      page: supply('/games', page()),
    })
    await wrapper.get('a').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('game-record')
    expect(router.currentRoute.value.params.gameId).toBe(gameId)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('同scopeの新参照では候補選択とページ要求を保持し、認証/tenant変更で初期ページへ戻す', async () => {
    const { wrapper } = await mountedEntry({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
    })
    await wrapper.get('select').setValue(gameId)
    await wrapper.get('nav button:last-child').trigger('click')
    expect(wrapper.text()).toContain('試合一覧：確認中')
    await wrapper.setProps({
      page: supply('/games', { ...page(), items: [...page().items] }),
      starts: supply('/games', [{ ...candidate }]),
    })
    expect(wrapper.get<HTMLSelectElement>('select').element.value).toBe(gameId)
    expect(wrapper.text()).toContain('試合一覧：確認中')

    const auth = useAuthStore(pinia)
    setVerifiedAuthForTest(auth, { teamId: tenantB, teamName: 'B' })
    await flushPromises()
    expect(wrapper.text()).toContain('試合一覧：未取得')
    expect(wrapper.text()).not.toContain('スタメン確定')
    await wrapper.setProps({
      page: {
        ...supply(
          '/games',
          page([
            {
              gameId: gameId2,
              tenantId: tenantB,
              label: '新tenantの試合',
              stateLabel: '準備中',
            },
          ]),
        ),
        tenantId: tenantB,
      },
      starts: {
        ...supply('/games', [
          { ...candidate, gameId: gameId2, tenantId: tenantB },
        ]),
        tenantId: tenantB,
      },
    })
    expect(wrapper.text()).toContain('新tenantの試合')
    expect(wrapper.get<HTMLSelectElement>('select').element.value).toBe('')
    expect(wrapper.text()).not.toContain('スタメン確定')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('同じ一覧instanceで経路を往復しても旧候補選択とページ要求を戻さない', async () => {
    const { wrapper, router } = await mountedEntry({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
    })
    await wrapper.get('select').setValue(gameId)
    await wrapper.get('nav button:last-child').trigger('click')
    await router.push(`/games/${gameId}/record`)
    await router.push('/games')
    await flushPromises()
    expect(wrapper.text()).toContain('試合A')
    expect(wrapper.get<HTMLSelectElement>('select').element.value).toBe('')
    expect(wrapper.text()).not.toContain('スタメン確定')
  })

  it('一覧のtenantと認証世代を個別に変えても旧選択/ページキーを戻さない', async () => {
    const { wrapper } = await mountedEntry({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
    })
    const auth = useAuthStore(pinia)
    await wrapper.get('select').setValue(gameId)
    await wrapper.get('nav button:last-child').trigger('click')
    auth.teamId = tenantB
    await flushPromises()
    auth.teamId = tenantA
    await flushPromises()
    expect(wrapper.text()).toContain('試合A')
    expect(wrapper.get<HTMLSelectElement>('select').element.value).toBe('')

    await wrapper.get('select').setValue(gameId)
    await wrapper.get('nav button:last-child').trigger('click')
    auth.authEpoch += 1
    await flushPromises()
    await wrapper.setProps({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
    })
    expect(wrapper.text()).toContain('試合A')
    expect(wrapper.get<HTMLSelectElement>('select').element.value).toBe('')
  })

  it('開始候補・スタメン・規則・権利・状態を表示するが実開始しない', async () => {
    const { wrapper } = await mountedEntry({
      starts: supply('/games', [candidate]),
      environment: supply('/games', environment),
    })
    await wrapper.get('select').setValue(gameId)
    expect(wrapper.text()).toContain('スタメン確定')
    expect(wrapper.text()).toContain('九回制')
    expect(wrapper.text()).toContain('記録権保持')
    const lineup = wrapper
      .findAll('button')
      .find((button) => button.text().includes('スタメンを確認・設定'))!
    expect(lineup.attributes('disabled')).toBeDefined()
    lineup.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    const start = wrapper
      .findAll('button')
      .find((button) => button.text().includes('試合を開始'))!
    expect(start.attributes('disabled')).toBeDefined()
    start.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('start')).toBeUndefined()
    expect(wrapper.text()).not.toContain('開始しました')
  })

  it.each(['pending', 'denied', 'failed'] as const)(
    '%sは取得済み成功にしない',
    async (status) => {
      const { wrapper } = await mountedEntry({
        page: { ...supply('/games', page()), status },
        starts: { ...supply('/games', [candidate]), status },
      })
      expect(wrapper.text()).not.toContain('試合A')
      expect(wrapper.find('select').exists()).toBe(false)
      expect(wrapper.text()).toContain(
        status === 'pending'
          ? '確認中'
          : status === 'denied'
            ? '確認できません'
            : '読み取れません',
      )
    },
  )

  it('中断中の再開入口・非保持・下書き復元未提供を表示して操作を封鎖する', async () => {
    const detail: RecordDetail = {
      ...candidate,
      existingState: 'suspended',
      recordingRight: 'denied',
      draftRestoration: { status: 'pending' },
    }
    const path = `/games/${gameId}/record`
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, detail),
    })
    expect(wrapper.text()).toContain('中断中の試合です')
    expect(wrapper.text()).toContain('記録権を保持していません')
    expect(wrapper.text()).toContain('下書き復元確認中')
    expect(wrapper.findComponent(GameScreen).exists()).toBe(false)
    expect(wrapper.find('[data-testid="pitch-speed"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('閲覧と未送信キューの保持は続けられます')
    const reopen = wrapper
      .findAll('button')
      .find((button) => button.text().includes('記録を再開'))!
    expect(reopen.attributes('disabled')).toBeDefined()
    reopen.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('不正ID・未知ID・他tenantの詳細は取得済み成功や存在情報を表示しない', async () => {
    const path = `/games/${gameId}/record`
    const detail: RecordDetail = {
      ...candidate,
      draftRestoration: { status: 'ready', value: '下書きあり' },
    }
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, detail),
    })
    expect(wrapper.text()).toContain('下書きあり')
    await wrapper.setProps({
      detail: supply(path, { ...detail, gameId: gameId2 }),
    })
    expect(wrapper.text()).toContain('試合詳細・記録権・下書き復元：未取得')
    await wrapper.setProps({
      detail: supply(path, { ...detail, tenantId: tenantB }),
    })
    expect(wrapper.text()).not.toContain('下書きあり')
    const bad = await mountedRecord('/games/not-uuid/record', {
      detail: supply('/games/not-uuid/record', detail),
    })
    expect(bad.wrapper.text()).toContain('試合IDが正しくありません')
    expect(bad.wrapper.text()).not.toContain('下書きあり')
    expect(bad.wrapper.find('[data-testid="pitch-speed"]').exists()).toBe(false)
    expect(bad.wrapper.text()).toContain('未送信キューは変更しません')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('記録権の非保持は未取得と分け、非保持への切替で旧入力を破棄する', async () => {
    const path = `/games/${gameId}/record`
    const held: RecordDetail = {
      ...candidate,
      draftRestoration: { status: 'pending' },
    }
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, held),
    })
    await wrapper
      .get<HTMLInputElement>('[data-testid="pitch-speed"]')
      .setValue('151')
    await wrapper.setProps({
      detail: supply(path, { ...held, recordingRight: 'denied' }),
    })
    expect(wrapper.text()).toContain('記録権を保持していません')
    expect(wrapper.text()).toContain('非保持')
    expect(wrapper.find('[data-testid="pitch-speed"]').exists()).toBe(false)
    await wrapper.setProps({ detail: supply(path, held) })
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    await wrapper.setProps({
      detail: { ...supply(path, held), status: 'denied' },
    })
    expect(wrapper.find('[data-testid="pitch-speed"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('閲覧と未送信キューの保持は続けられます')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('実GameScreenの球速下書きは同じ試合の再供給で残し、試合route変更で消す', async () => {
    const path = `/games/${gameId}/record`
    const nextPath = `/games/${gameId2}/record`
    const detail: RecordDetail = {
      ...candidate,
      draftRestoration: { status: 'ready', value: '現在の試合' },
    }
    const { wrapper, router } = await mountedRecord(path, {
      detail: supply(path, detail),
    })
    const firstInstance = wrapper.getComponent(GameScreen).vm.$.uid
    await wrapper
      .get<HTMLInputElement>('[data-testid="pitch-speed"]')
      .setValue('145')
    await wrapper.setProps({
      detail: supply(path, { ...detail, lineup: { ...detail.lineup } }),
    })
    expect(wrapper.getComponent(GameScreen).vm.$.uid).toBe(firstInstance)
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('145')

    await router.push(nextPath)
    await flushPromises()
    expect(wrapper.getComponent(GameScreen).vm.$.uid).not.toBe(firstInstance)
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    expect(wrapper.text()).not.toContain('現在の試合')
    expect(wrapper.text()).toContain('試合詳細・記録権・下書き復元：未取得')
    await wrapper.setProps({
      detail: supply(nextPath, {
        ...detail,
        gameId: gameId2,
        label: '次の試合',
        draftRestoration: { status: 'pending' },
      }),
    })
    expect(wrapper.text()).toContain('次の試合')
    expect(wrapper.text()).not.toContain('現在の試合')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('実GameScreenの球速下書きと旧metadataは認証再検証/tenant切替で消える', async () => {
    const path = `/games/${gameId}/record`
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, {
        ...candidate,
        label: '旧tenantの試合',
        draftRestoration: { status: 'ready', value: '旧下書き' },
      }),
      environment: supply(path, environment),
    })
    const initialInstance = wrapper.getComponent(GameScreen).vm.$.uid
    await wrapper
      .get<HTMLInputElement>('[data-testid="pitch-speed"]')
      .setValue('152')
    const auth = useAuthStore(pinia)
    auth.beginSessionVerification()
    await flushPromises()
    expect(wrapper.findComponent(GameScreen).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('旧tenantの試合')
    expect(wrapper.text()).not.toContain('旧下書き')
    expect(wrapper.text()).toContain('未送信件数：未取得')

    setVerifiedAuthForTest(auth, { teamId: tenantB, teamName: 'B' })
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧tenantの試合')
    expect(wrapper.getComponent(GameScreen).vm.$.uid).not.toBe(initialInstance)
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('tenantと認証世代の個別変更でも実GameScreenを再生成する', async () => {
    const path = `/games/${gameId}/record`
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, {
        ...candidate,
        label: '旧詳細',
        draftRestoration: { status: 'ready', value: '旧下書き' },
      }),
    })
    const auth = useAuthStore(pinia)
    const first = wrapper.getComponent(GameScreen).vm.$.uid
    await wrapper
      .get<HTMLInputElement>('[data-testid="pitch-speed"]')
      .setValue('141')
    auth.teamId = tenantB
    await flushPromises()
    const second = wrapper.getComponent(GameScreen).vm.$.uid
    expect(second).not.toBe(first)
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    expect(wrapper.text()).not.toContain('旧詳細')
    auth.teamId = tenantA
    await flushPromises()
    await wrapper
      .get<HTMLInputElement>('[data-testid="pitch-speed"]')
      .setValue('142')
    const third = wrapper.getComponent(GameScreen).vm.$.uid
    auth.authEpoch += 1
    await flushPromises()
    expect(wrapper.getComponent(GameScreen).vm.$.uid).not.toBe(third)
    expect(
      wrapper.get<HTMLInputElement>('[data-testid="pitch-speed"]').element
        .value,
    ).toBe('')
    expect(wrapper.text()).not.toContain('旧詳細')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('他tenantの一覧項目と不正IDを含むページを丸ごと未取得にする', async () => {
    const { wrapper } = await mountedEntry({ page: supply('/games', page()) })
    await wrapper.setProps({
      page: supply(
        '/games',
        page([
          {
            gameId,
            tenantId: tenantA,
            label: '表示対象',
            stateLabel: '中断中',
          },
          {
            gameId: gameId2,
            tenantId: tenantB,
            label: '秘匿対象',
            stateLabel: '進行中',
          },
        ]),
      ),
    })
    expect(wrapper.text()).toContain('試合一覧：未取得')
    expect(wrapper.text()).not.toContain('秘匿対象')
    expect(wrapper.text()).not.toContain('表示対象')
    await wrapper.setProps({
      page: supply(
        '/games',
        page([
          {
            gameId: 'NOT-UUID',
            tenantId: tenantA,
            label: '不正',
            stateLabel: '進行中',
          },
        ]),
      ),
    })
    expect(wrapper.text()).toContain('試合一覧：未取得')
    expect(wrapper.text()).not.toContain('不正')
  })

  it('null/疎配列/未知状態/不正datumの候補とページは安全に未取得へ倒す', async () => {
    const { wrapper } = await mountedEntry({
      page: supply('/games', page()),
      starts: supply('/games', [candidate]),
    })
    const sparseCandidates = new Array<StartCandidate>(2)
    sparseCandidates[0] = candidate
    const brokenCandidates: unknown[] = [
      null,
      sparseCandidates,
      [{ ...candidate, existingState: 'constructor' }],
      [{ ...candidate, lineup: null }],
      [{ ...candidate, rules: { status: 'ready', value: null } }],
    ]
    for (const malformed of brokenCandidates) {
      await wrapper.setProps({
        starts: supply('/games', malformed as readonly StartCandidate[]),
      })
      expect(wrapper.text()).toContain('開始候補・スタメン・適用規則：未取得')
      expect(wrapper.find('select').exists()).toBe(false)
      expect(wrapper.text()).toContain('試合A')
    }
    const sparseItems = new Array<GameListPage['items'][number]>(2)
    sparseItems[0] = page().items[0]!
    for (const malformed of [
      null,
      { ...page(), items: sparseItems },
      { ...page(), items: [null] },
    ]) {
      await wrapper.setProps({
        page: supply('/games', malformed as GameListPage),
      })
      expect(wrapper.text()).toContain('試合一覧：未取得')
      expect(wrapper.text()).not.toContain('試合A')
      expect(
        wrapper
          .findAll('button')
          .find((button) => button.text().includes('試合を開始'))
          ?.attributes('disabled'),
      ).toBeDefined()
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['constructor', '__proto__', 'toString', null, {}, 0])(
    '未知の既存状態%jを内部値として表示しない',
    (state) => {
      expect(existingStateLabel(state)).toBe('未取得')
    },
  )

  it('壊れた詳細は旧metadataを消し、GameScreenの閲覧と確定封鎖を維持する', async () => {
    const path = `/games/${gameId}/record`
    const detail: RecordDetail = {
      ...candidate,
      label: '旧詳細',
      draftRestoration: { status: 'ready', value: '旧下書き' },
    }
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, detail),
    })
    for (const malformed of [
      null,
      new Array(1),
      { ...detail, existingState: '__proto__' },
      { ...detail, draftRestoration: null },
      { ...detail, draftRestoration: { status: 'ready', value: null } },
    ]) {
      await wrapper.setProps({
        detail: supply(path, malformed as RecordDetail),
      })
      expect(wrapper.text()).toContain('試合詳細・記録権・下書き復元：未取得')
      expect(wrapper.text()).not.toContain('旧詳細')
      expect(wrapper.text()).not.toContain('旧下書き')
      expect(wrapper.findComponent(GameScreen).exists()).toBe(true)
      expect(
        wrapper.get('[data-testid="commit-pitch"]').attributes('disabled'),
      ).toBeDefined()
    }
    expect(wrapper.text()).toContain('記録の確定・保存・送信はできません')
    expect(wrapper.text()).not.toContain('入力・保存・送信はできません')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('記録画面の全ての実操作は直接dispatchでも無動作でPOSTしない', async () => {
    const path = `/games/${gameId}/record`
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, {
        ...candidate,
        draftRestoration: { status: 'ready', value: '復元待ち' },
      }),
      environment: supply(path, environment),
    })
    const operations = wrapper
      .findAll('button')
      .filter((button) =>
        /開始|再開|確定|送信|訂正|終了|交代|取消|保存/.test(button.text()),
      )
    expect(operations.length).toBeGreaterThan(0)
    for (const button of operations) {
      expect(button.attributes('disabled')).toBeDefined()
      button.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(
      Object.keys(wrapper.emitted()).filter((name) => name !== 'click'),
    ).toEqual([])
    expect(wrapper.text()).not.toContain('保存しました')
  })

  it.each([375, 320])(
    '%ipxで長文を縦積み折返し、利用者文字列をescapeする',
    async (width) => {
      window.innerWidth = width
      const unsafe = '<img src=x onerror=alert(1)>' + '長い試合名'.repeat(30)
      const { wrapper } = await mountedEntry({
        page: supply(
          '/games',
          page([
            { gameId, tenantId: tenantA, label: unsafe, stateLabel: '中断中' },
          ]),
        ),
        starts: supply('/games', [{ ...candidate, label: unsafe }]),
      })
      expect(wrapper.text()).toContain(unsafe)
      expect(wrapper.find('img').exists()).toBe(false)
      expect(wrapper.html()).toContain('&lt;img')
      expect(wrapper.classes()).toContain('wrap-anywhere')
      expect(wrapper.get('nav').classes()).toContain('flex-col')
      expect(wrapper.get('select').classes()).toContain('min-w-0')
    },
  )
})

describe('NFR-020 の提供済み前提表示', () => {
  it.each([
    ['offline', [1], 'granted'],
    ['unknown', [5], 'granted'],
    ['offline', [6], 'denied'],
    ['unknown', [1, 5, 6], 'denied'],
    ['offline', [], 'denied'],
  ] as const)(
    '通信%s・前提不足%j・永続化%sを別々に示し、開始を封鎖する',
    async (connectivity, missing, persistence) => {
      const premises: EntryEnvironment['premises'] = {
        1: 'met',
        5: 'met',
        6: 'met',
      }
      for (const number of missing) premises[number] = 'unmet'
      const { wrapper } = await mountedEntry({
        page: supply('/games', page()),
        environment: supply('/games', {
          ...environment,
          connectivity,
          premises,
          persistence,
        }),
      })
      expect(wrapper.text()).toContain(
        connectivity === 'offline'
          ? '通信状態：オフライン'
          : '通信状態：未取得',
      )
      expect(wrapper.text()).toContain('試合を開始・再開できません')
      for (const number of missing) {
        const content =
          number === 1
            ? 'トップレベルの HTTPS 表示'
            : number === 5
              ? 'サイトストレージが利用可能'
              : 'Lockdown Mode 非適用'
        expect(wrapper.text()).toContain(`前提${number} ${content}：不成立`)
      }
      expect(wrapper.text().includes('永続化保証の要求が拒否されました')).toBe(
        persistence === 'denied' && !missing.some((number) => number === 5),
      )
      expect(wrapper.text()).toContain('未送信件数：4')
      expect(wrapper.text()).toContain('試合の閲覧はできます')
      expect(wrapper.text()).toContain('試合A')
      const start = wrapper
        .findAll('button')
        .find((button) => button.text().includes('試合を開始'))!
      expect(start.attributes('disabled')).toBeDefined()
      start.element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it('通信状態を省略・不正・他tenant・旧認証世代・別経路からオンラインに昇格しない', async () => {
    const { wrapper } = await mountedEntry({
      environment: supply('/games', environment),
    })
    expect(wrapper.text()).toContain('通信状態：オンライン（提供された状態）')
    await wrapper.setProps({ environment: undefined })
    expect(wrapper.text()).toContain('通信状態：未取得')
    for (const malformed of [
      { ...environment, connectivity: 'bad' },
      { ...environment, premises: null },
      { ...environment, persistence: 'bad' },
      { ...environment, queuedCount: -1 },
    ]) {
      await wrapper.setProps({
        environment: supply('/games', malformed as unknown as EntryEnvironment),
      })
      expect(wrapper.text()).toContain('通信状態：未取得')
      expect(wrapper.text()).not.toContain('通信状態：オンライン')
    }
    for (const status of ['pending', 'failed', 'denied'] as const) {
      await wrapper.setProps({
        environment: { ...supply('/games', environment), status },
      })
      expect(wrapper.text()).toContain('通信状態：未取得')
      expect(wrapper.text()).not.toContain('通信状態：オンライン')
    }
    for (const stale of [
      { ...supply('/games', environment), tenantId: tenantB },
      { ...supply('/games', environment), authEpoch: -1 },
      supply('/games/other', environment),
      supply('/games', environment, 'old-request'),
    ]) {
      await wrapper.setProps({ environment: stale })
      expect(wrapper.text()).toContain('通信状態：未取得')
      expect(wrapper.text()).not.toContain('通信状態：オンライン')
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('中断した試合と通信断を区別し、記録画面でも再開を封鎖する', async () => {
    const path = `/games/${gameId}/record`
    const { wrapper } = await mountedRecord(path, {
      detail: supply(path, {
        ...candidate,
        existingState: 'suspended',
        draftRestoration: { status: 'pending' },
      }),
      environment: supply(path, { ...environment, connectivity: 'offline' }),
    })
    expect(wrapper.text()).toContain('中断中の試合です')
    expect(wrapper.text()).toContain('通信状態：オフライン')
    expect(wrapper.text()).toContain(
      '通信が切れているため、試合を開始・再開できません',
    )
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text().includes('記録を再開'))
        ?.attributes('disabled'),
    ).toBeDefined()
    expect(
      wrapper.get('[data-testid="commit-pitch"]').attributes('disabled'),
    ).toBeDefined()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([
    [[1], 'トップレベルの HTTPS 表示'],
    [[5], 'サイトストレージが利用可能'],
    [[6], 'Lockdown Mode 非適用'],
    [[1, 5], 'サイトストレージが利用可能'],
    [[1, 5, 6], 'Lockdown Mode 非適用'],
  ] as const)(
    '不足%jを全番号/内容で表示し、キュー保持と閲覧を保つ',
    async (missing, content) => {
      const premises: EntryEnvironment['premises'] = {
        1: 'met',
        5: 'met',
        6: 'met',
      }
      for (const number of missing) premises[number] = 'unmet'
      const { wrapper } = await mountedEntry({
        page: supply('/games', page()),
        environment: supply('/games', { ...environment, premises }),
      })
      expect(wrapper.text()).toContain(content)
      for (const number of missing)
        expect(wrapper.text()).toContain(`前提${number}`)
      for (const number of missing)
        expect(wrapper.text()).toContain(
          number === 1
            ? 'トップレベルの HTTPS 表示'
            : number === 5
              ? 'サイトストレージが利用可能'
              : 'Lockdown Mode 非適用',
        )
      expect(wrapper.text()).toContain('未送信件数：4')
      expect(wrapper.text()).toContain('試合の閲覧はできます')
      expect(wrapper.text()).toContain('試合A')
      expect(
        wrapper
          .findAll('button')
          .find((button) => button.text().includes('試合を開始'))
          ?.attributes('disabled'),
      ).toBeDefined()
      expect(fetchMock).not.toHaveBeenCalled()
    },
  )

  it('未知前提を成立扱いせず、persistだけ拒否なら警告と区別する', async () => {
    const { wrapper } = await mountedEntry({
      environment: supply('/games', {
        ...environment,
        premises: { 1: 'met', 5: 'met', 6: 'unknown' },
        persistence: 'denied',
      }),
    })
    expect(wrapper.text()).toContain('前提6 Lockdown Mode 非適用：不明')
    expect(wrapper.text()).toContain('永続化保証の要求が拒否されました')
    await wrapper.setProps({
      environment: supply('/games', { ...environment, persistence: 'denied' }),
    })
    expect(wrapper.text()).not.toContain(
      '前提5 サイトストレージが利用可能：不成立',
    )
    expect(wrapper.text()).toContain(
      'この警告だけでは開始前提5の不成立ではありません',
    )
    await wrapper.setProps({
      environment: supply('/games', {
        ...environment,
        premises: { 1: 'met', 5: 'unmet', 6: 'met' },
        persistence: 'denied',
      }),
    })
    expect(wrapper.text()).toContain('前提5 サイトストレージが利用可能：不成立')
    expect(wrapper.text()).not.toContain(
      'この警告だけでは開始前提5の不成立ではありません',
    )
  })
})

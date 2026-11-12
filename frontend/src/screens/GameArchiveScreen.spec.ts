import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { installAppProviders, pinia } from '../appProviders'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import GameArchiveScreen from './GameArchiveScreen.vue'

const mocks = vi.hoisted(() => ({
  listGameArchive: vi.fn(),
  listTeamRecords: vi.fn(),
}))
vi.mock('../api/games', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/games')>()
  return { ...actual, listGameArchive: mocks.listGameArchive }
})
vi.mock('../api/roster', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/roster')>()
  return { ...actual, listTeamRecords: mocks.listTeamRecords }
})

const tenant = '11111111-1111-4111-8111-111111111111'
const away = '22222222-2222-4222-8222-222222222222'
const home = '33333333-3333-4333-8333-333333333333'
const gameId = '44444444-4444-4444-8444-444444444444'
const wrappers: VueWrapper[] = []
const provider = { install: installAppProviders }

function archiveGame(overrides: Record<string, unknown> = {}) {
  return {
    id: gameId,
    scheduled_at: '2026-11-12T10:00:00+09:00',
    game_type_key: 'game_official',
    tournament_key: 'tournament',
    away_team_record_id: away,
    home_team_record_id: home,
    status: 'in_progress',
    started_at: '2026-11-12T10:01:00+09:00',
    ...overrides,
  }
}

async function mounted() {
  const router = createAppRouter(createMemoryHistory())
  await router.push('/games/archive')
  const wrapper = mount(GameArchiveScreen, {
    global: { plugins: [provider, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  mocks.listGameArchive.mockReset()
  mocks.listTeamRecords.mockReset()
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: tenant,
    teamName: '筑波大学',
  })
  mocks.listTeamRecords.mockResolvedValue({
    items: [
      { id: away, kind: 'opponent', name: '東京大学', hidden_at: null },
      { id: home, kind: 'self', name: '筑波大学', hidden_at: null },
    ],
    next_cursor: null,
  })
  mocks.listGameArchive.mockResolvedValue({
    items: [
      archiveGame(),
      archiveGame({ id: home, status: 'preparing', started_at: null }),
      archiveGame({ id: away, status: 'finished' }),
    ],
    next_cursor: 'next-page',
  })
})
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
})

it('3状態のカードとチーム名、各入口を表示する', async () => {
  const wrapper = await mounted()
  expect(wrapper.text()).toContain('東京大学')
  expect(wrapper.text()).toContain('筑波大学')
  expect(wrapper.text()).toContain('進行中')
  expect(wrapper.text()).toContain('準備中')
  expect(wrapper.text()).toContain('終了')
  expect(wrapper.findAll('article')).toHaveLength(3)
  expect(wrapper.text()).toContain('再開')
  expect(wrapper.text()).toContain('開始')
  expect(wrapper.text()).toContain('追記・再開')
  expect(wrapper.findAll('a').map((link) => link.attributes('href'))).toEqual(
    expect.arrayContaining([
      `/games/${gameId}/record`,
      `/games/${gameId}/view`,
      `/games/${gameId}/stats`,
      `/games/${gameId}/export`,
    ]),
  )
})

it('状態フィルタとページ内検索でカードを絞り込む', async () => {
  const wrapper = await mounted()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '終了')!
    .trigger('click')
  expect(wrapper.findAll('article')).toHaveLength(1)
  expect(wrapper.text()).toContain('終了')
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'すべて')!
    .trigger('click')
  await wrapper.get('input[type="search"]').setValue('東京大学')
  expect(wrapper.findAll('article')).toHaveLength(3)
  await wrapper.get('input[type="search"]').setValue('該当なし')
  expect(wrapper.findAll('article')).toHaveLength(0)
  expect(wrapper.text()).toContain('条件に一致する試合がありません')
})

it('次のページで返却cursorを使い、前のページで戻る', async () => {
  const wrapper = await mounted()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '次のページ')!
    .trigger('click')
  await flushPromises()
  expect(mocks.listGameArchive).toHaveBeenLastCalledWith(
    'next-page',
    expect.any(AbortSignal),
  )
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '前のページ')!
    .trigger('click')
  await flushPromises()
  expect(mocks.listGameArchive).toHaveBeenLastCalledWith(
    null,
    expect.any(AbortSignal),
  )
})

it('取得失敗を再試行でき、チーム名が取れなくてもIDで表示する', async () => {
  mocks.listTeamRecords.mockRejectedValue(new Error('team failed'))
  mocks.listGameArchive.mockRejectedValueOnce(new Error('archive failed'))
  const wrapper = await mounted()
  expect(wrapper.text()).toContain('試合一覧を取得できませんでした')
  mocks.listGameArchive.mockResolvedValueOnce({
    items: [archiveGame()],
    next_cursor: null,
  })
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '再試行')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.findAll('article')).toHaveLength(1)
  expect(wrapper.text()).toContain(`チーム ${away.slice(0, 8)}`)
})

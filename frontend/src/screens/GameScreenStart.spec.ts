import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { computed, readonly, shallowRef } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import type { PreparingGame } from '../api/games'
import { installAppProviders, pinia } from '../appProviders'
import { queryClient } from '../lib/queryClient'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import type { GameStartLineups, GameStartView } from './GameScreenStartProvider'
import GameScreenStart from './GameScreenStart.vue'

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const away = '20000000-0000-4000-8000-000000000001'
const path = `/games/${game}/record`
const wrappers: VueWrapper[] = []
function saved(dh: boolean): PreparingGame {
  return {
    id: game,
    scheduled_at: '2026-10-26T10:00:00+09:00',
    game_type_key: 'game_other',
    tournament_key: 'none',
    away_team_record_id: away,
    home_team_record_id: tenant,
    plate_umpire: null,
    section_label: null,
    week_label: null,
    day_label: null,
    game_number_label: null,
    status: 'preparing',
    applied_rules: { dh },
  }
}
function players(team: string, offset = 0) {
  return Array.from({ length: 20 }, (_, index) => ({
    id: `${team === away ? '3' : '4'}0000000-0000-4000-8000-${String(index + offset + 1).padStart(12, '0')}`,
    team_record_id: team,
    name: `選手${index + offset + 1}`,
    uniform_number: String(index + offset + 1),
    roster_status_key: 'active',
    hidden_at: null,
  }))
}
function response(value: unknown, init?: RequestInit) {
  return new Response(JSON.stringify(value), {
    headers: {
      'Content-Type': 'application/json',
      'X-Pitchlog-Tenant-Match': '1',
      'X-Pitchlog-Tenant-Challenge':
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge') ?? '',
    },
  })
}
function connection(registered = true) {
  const state = shallowRef<GameStartView>({
    phase: 'ready',
    deviceReady: registered,
    savedRequest: false,
    startedAt: null,
    message: '開始入力を確認できます',
  })
  const value = {
    state: readonly(state),
    canEnroll: computed(
      () => state.value.phase === 'ready' && !state.value.deviceReady,
    ),
    canStart: computed(
      () => state.value.phase === 'ready' && state.value.deviceReady,
    ),
    canResolve: computed(
      () => state.value.phase === 'unknown' && state.value.savedRequest,
    ),
    enroll: vi.fn(async () => {
      state.value = { ...state.value, deviceReady: true }
    }),
    start: vi
      .fn<(lineups: GameStartLineups) => Promise<void>>()
      .mockResolvedValue(undefined),
    resolve: vi.fn(async () => {}),
  }
  return { value, state }
}
async function view(dh = false, registered = true) {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const api = connection(registered)
  const preparing = {
    tenantId: tenant,
    authEpoch: useAuthStore(pinia).authEpoch,
    path,
    requestKey: game,
    status: 'ready' as const,
    data: { tenantId: tenant, gameId: game, label: '試合', saved: saved(dh) },
  }
  const wrapper = mount(GameScreenStart, {
    props: { preparing, connection: api.value },
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, api, router, preparing }
}
async function fill(wrapper: VueWrapper, dh: boolean) {
  for (const [side, team] of [
    ['away', away],
    ['home', tenant],
  ] as const) {
    for (let index = 0; index < (dh ? 10 : 9); index += 1) {
      await wrapper
        .find(`#start-${side}-${index}-player`)
        .setValue(players(team)[index]!.id)
      await wrapper
        .find(`#start-${side}-${index}-position`)
        .setValue(
          dh && index === 0 ? 'DH' : index === 9 ? '1' : String(index + 1),
        )
    }
  }
}
function button(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find((value) => value.text() === text)!
}
beforeEach(() => {
  localStorage.clear()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    onLine: true,
    locks: {
      request: vi.fn(async (_n, _o, action) => action({ name: 'start-ui' })),
    },
  })
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamName: '試験',
    teamId: tenant,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
      const query = new URL(String(url), 'https://test').searchParams
      return response(
        { items: players(query.get('team_record_id')!), next_cursor: null },
        init,
      )
    }),
  )
})
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  queryClient.clear()
})

it.each([false, true])(
  '利用者が全枠を選んだ実入力だけを開始へ渡す（DH=%s）',
  async (dh) => {
    const { wrapper, api } = await view(dh)
    expect(fetch).toHaveBeenCalledTimes(2)
    for (const [url, init] of vi.mocked(fetch).mock.calls) {
      const query = new URL(String(url), 'https://test').searchParams
      expect(query.get('limit')).toBe('20')
      expect(query.get('include_hidden')).toBe('false')
      expect(query.get('roster_status_key')).toBe('active')
      expect(new Headers(init?.headers).get('X-Pitchlog-Expected-Tenant')).toBe(
        tenant,
      )
    }
    expect(button(wrapper, '試合を開始').attributes('disabled')).toBeDefined()
    await wrapper.find('form').trigger('submit')
    expect(api.value.start).not.toHaveBeenCalled()
    await fill(wrapper, dh)
    expect(button(wrapper, '試合を開始').attributes('disabled')).toBeUndefined()
    await wrapper.find('form').trigger('submit')
    expect(api.value.start).toHaveBeenCalledTimes(1)
    const value = api.value.start.mock.calls[0]![0]
    for (const [side, team] of [
      ['away', away],
      ['home', tenant],
    ] as const) {
      expect(value[side]).toEqual(
        Array.from({ length: dh ? 10 : 9 }, (_, index) => ({
          player_id: players(team)[index]!.id,
          batting_order: index < 9 ? index + 1 : null,
          fielding_position:
            dh && index === 0
              ? { kind: 'designated-hitter' }
              : {
                  kind: 'fielding',
                  position: index === 9 ? 1 : index + 1,
                },
        })),
      )
    }
  },
)

it('端末資格の保存前は選手入力・取得を開かず、明示登録後に開く', async () => {
  const { wrapper, api } = await view(false, false)
  expect(wrapper.find('select').exists()).toBe(false)
  expect(fetch).not.toHaveBeenCalled()
  await button(wrapper, 'この端末を登録').trigger('click')
  await flushPromises()
  expect(api.value.enroll).toHaveBeenCalledTimes(1)
  expect(wrapper.find('select').exists()).toBe(true)
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('選手名をHTMLとして描画しない', async () => {
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const team = new URL(String(url), 'https://test').searchParams.get(
      'team_record_id',
    )!
    const rows = players(team)
    rows[0]!.name = '<img src=x onerror=alert(1)>'
    return response({ items: rows, next_cursor: null }, init)
  })
  const { wrapper } = await view()
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('option').element.textContent).toBe('選択してください')
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
})

it.each(['team', 'hidden', 'inactive', 'duplicate', 'cursor'])(
  '%sの不正選手応答を採用せず自動再取得しない',
  async (fault) => {
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      const team = new URL(String(url), 'https://test').searchParams.get(
        'team_record_id',
      )!
      const rows = players(team)
      if (fault === 'team') rows[0]!.team_record_id = game
      if (fault === 'hidden')
        Object.assign(rows[0]!, { hidden_at: '2026-10-26' })
      if (fault === 'inactive') rows[0]!.roster_status_key = 'inactive'
      if (fault === 'duplicate') rows[1]!.id = rows[0]!.id
      return response(
        { items: rows, next_cursor: fault === 'cursor' ? 1 : null },
        init,
      )
    })
    const { wrapper, api } = await view()
    expect(wrapper.text()).toContain('選手を取得できません')
    expect(wrapper.find('#start-away-0-player').findAll('option')).toHaveLength(
      1,
    )
    expect(button(wrapper, '試合を開始').attributes('disabled')).toBeDefined()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(api.value.start).not.toHaveBeenCalled()
  },
)

it('明示ページ送りだけを行い、前ページの選択を保持する', async () => {
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const query = new URL(String(url), 'https://test').searchParams
    const offset = query.get('cursor') === 'page2' ? 20 : 0
    return response(
      {
        items: players(query.get('team_record_id')!, offset),
        next_cursor: offset === 0 ? 'page2' : null,
      },
      init,
    )
  })
  const { wrapper } = await view()
  const selected = players(away)[0]!
  await wrapper.find('#start-away-0-player').setValue(selected.id)
  await button(wrapper, '先攻の次のページ').trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledTimes(3)
  expect(
    (wrapper.find('#start-away-0-player').element as HTMLSelectElement).value,
  ).toBe(selected.id)
  expect(
    wrapper.find(`#start-away-0-player option[value="${selected.id}"]`).text(),
  ).toContain(selected.name)
  expect(
    new URL(
      String(vi.mocked(fetch).mock.calls[2]![0]),
      'https://test',
    ).searchParams.get('cursor'),
  ).toBe('page2')
})

it('DH不明をfalseへ補わず、別認証scopeへ選択を持ち越さない', async () => {
  const { wrapper, preparing } = await view()
  await fill(wrapper, false)
  await wrapper.setProps({
    preparing: {
      ...preparing,
      data: {
        ...preparing.data,
        saved: { ...preparing.data.saved, applied_rules: {} },
      },
    },
  })
  expect(wrapper.find('select').exists()).toBe(false)
  await wrapper.setProps({ preparing })
  await flushPromises()
  expect(
    (wrapper.find('#start-away-0-player').element as HTMLSelectElement).value,
  ).toBe('')
  setVerifiedAuthForTest(useAuthStore(pinia), { teamName: '別', teamId: away })
  await flushPromises()
  expect(wrapper.find('select').exists()).toBe(false)
})

it('未解決要求では新規開始入力を出さず明示照会だけを渡す', async () => {
  const { wrapper, api } = await view()
  api.state.value = {
    phase: 'unknown',
    deviceReady: true,
    savedRequest: true,
    startedAt: null,
    message: '結果は未確認です',
  }
  await flushPromises()
  expect(wrapper.find('form').exists()).toBe(false)
  await button(wrapper, '保存した開始要求の結果を確認').trigger('click')
  expect(api.value.resolve).toHaveBeenCalledTimes(1)
  expect(api.value.start).not.toHaveBeenCalled()
})

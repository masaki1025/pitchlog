import { IDBFactory } from 'fake-indexeddb'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import type { PreparingGame } from '../api/games'
import { installAppProviders, pinia } from '../appProviders'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { queryClient } from '../lib/queryClient'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import GameScreen from './GameScreen.vue'
import GameScreenEntryRecordHost from './GameScreenEntryRecordHost.vue'

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const device = '10000000-0000-4000-8000-000000000003'
const away = '20000000-0000-4000-8000-000000000001'
const credential = 'public-host-device-credential'
const proof = 'public-host-recording-proof'
const path = `/games/${game}/record`
const saved: PreparingGame = {
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
  applied_rules: { dh: false },
}
const wrappers: VueWrapper[] = []
const stores: GameStartPersistence[] = []
function players(team: string) {
  return Array.from({ length: 9 }, (_, index) => ({
    id: `${team === away ? '3' : '4'}0000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    team_record_id: team,
    name: `選手${index + 1}`,
    uniform_number: String(index + 1),
    roster_status_key: 'active',
    hidden_at: null,
  }))
}
function response(value: unknown, init?: RequestInit, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...(status < 300
        ? {
            'X-Pitchlog-Tenant-Match': '1',
            'X-Pitchlog-Tenant-Challenge':
              new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge') ??
              '',
          }
        : {}),
    },
  })
}
async function view() {
  const router = createAppRouter(createMemoryHistory())
  await router.push(path)
  const wrapper = mount(GameScreenEntryRecordHost, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
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
      request: vi.fn(async (_n, _o, action) => action({ name: 'host-unit' })),
    },
  })
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('indexedDB', new IDBFactory())
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamName: '試験',
    teamId: tenant,
  })
})
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  for (const store of stores.splice(0)) store.close()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  queryClient.clear()
})

it('実hostから利用者選択→要求保存→POST→応答保存を接ぎ、reloadでは前回応答として復元する', async () => {
  let started = false
  let body: Record<string, unknown> | null = null
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>().mockImplementation(async (url, init) => {
      const target = new URL(String(url), 'https://test')
      if (
        target.pathname === `/api/games/${game}/started` &&
        init?.method === 'GET'
      )
        return response({ error: { message: 'Not Found' } }, init, 404)
      if (target.pathname === `/api/games/${game}` && init?.method === 'GET')
        return response(
          started ? { error: { message: 'Not Found' } } : saved,
          init,
          started ? 404 : 200,
        )
      if (target.pathname === '/api/devices/enroll')
        return response(
          {
            tenant_id: tenant,
            device_id: device,
            device_credential: credential,
          },
          init,
        )
      if (target.pathname === '/api/players')
        return response(
          {
            items: players(target.searchParams.get('team_record_id')!),
            next_cursor: null,
          },
          init,
        )
      if (target.pathname === `/api/games/${game}/start`) {
        started = true
        body = JSON.parse(init?.body as string) as Record<string, unknown>
        return response(
          {
            tenant_id: tenant,
            game_id: game,
            start_request_id: body.start_request_id,
            device_id: device,
            d4: 'opaque-host-reference',
            recovery_generation: '1',
            recording_right_proof: proof,
            started_at: '2026-10-26T12:34:56Z',
            away_lineup_id: away,
            home_lineup_id: game,
          },
          init,
        )
      }
      throw new Error('未登録の試験輸送経路')
    }),
  )
  const first = await view()
  await vi.waitFor(() =>
    expect(
      button(first, 'この端末を登録').attributes('disabled'),
    ).toBeUndefined(),
  )
  expect(first.find('select').exists()).toBe(false)
  await button(first, 'この端末を登録').trigger('click')
  await vi.waitFor(() =>
    expect(first.find('#start-away-0-player').findAll('option')).toHaveLength(
      10,
    ),
  )
  for (const [side, team] of [
    ['away', away],
    ['home', tenant],
  ] as const) {
    for (let index = 0; index < 9; index += 1) {
      await first
        .find(`#start-${side}-${index}-player`)
        .setValue(players(team)[index]!.id)
      await first
        .find(`#start-${side}-${index}-position`)
        .setValue(String(index + 1))
    }
  }
  await first.find('form').trigger('submit')
  await vi.waitFor(() =>
    expect(first.text()).toContain('開始応答を保存しました'),
  )
  expect(first.findComponent(GameScreen).exists()).toBe(false)
  for (const value of [credential, proof, 'opaque-host-reference'])
    expect(first.text()).not.toContain(value)
  const store = await GameStartPersistence.open()
  stores.push(store)
  const request = await store.readStart(tenant, game)
  expect(request?.status).toBe('received')
  expect(request?.request).toEqual(body)
  for (const side of ['away', 'home'] as const) {
    expect(
      request?.request[side].map((entry) => entry.fielding_position),
    ).toEqual(
      Array.from({ length: 9 }, (_, index) => ({
        kind: 'fielding',
        position: index + 1,
      })),
    )
  }
  expect(request?.grant?.recording_right_proof).toBe(proof)
  expect(
    vi
      .mocked(fetch)
      .mock.calls.filter(
        ([url, init]) =>
          String(url).endsWith('/start') && init?.method === 'POST',
      ),
  ).toHaveLength(1)
  first.unmount()
  wrappers.splice(wrappers.indexOf(first), 1)
  vi.mocked(fetch).mockClear()
  const reopened = await view()
  await vi.waitFor(() =>
    expect(reopened.text()).toContain('前回受領した開始応答'),
  )
  expect(reopened.text()).toContain('現在の記録権は未確認')
  expect(reopened.findComponent(GameScreen).exists()).toBe(false)
  expect(reopened.find('form').exists()).toBe(false)
  expect(
    vi.mocked(fetch).mock.calls.every(([, init]) => init?.method === 'GET'),
  ).toBe(true)
  expect(await store.readStart(tenant, game)).toEqual(request)
})

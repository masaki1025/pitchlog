import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import { listPreparingGames, readPreparingGame } from './games'
const tenant = '11111111-1111-4111-8111-111111111111'
const id = '22222222-2222-4222-8222-222222222222'
let pinia: Pinia
const game = {
  id,
  scheduled_at: '2026-10-24T10:00:00+09:00',
  game_type_key: 'game_open',
  tournament_key: '<svg onload=alert(1)>',
  away_team_record_id: tenant,
  home_team_record_id: id,
  plate_umpire: null,
  section_label: '保存ラベル',
  week_label: null,
  day_label: null,
  game_number_label: null,
  status: 'preparing',
  applied_rules: { regulationInnings: 9, dh: true, saved: '<b>保存値</b>' },
}
let body: unknown
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'A' })
  body = game
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (_url, init) =>
        new Response(JSON.stringify(body), {
          headers: {
            'Content-Type': 'application/json',
            'X-Pitchlog-Tenant-Match': '1',
            'X-Pitchlog-Tenant-Challenge': new Headers(init?.headers).get(
              'X-Pitchlog-Tenant-Challenge',
            )!,
          },
        }),
    ),
  )
})
afterEach(() => {
  disposePinia(pinia)
  vi.unstubAllGlobals()
})
it('GET2経路を正規C2・Cookie・signalで送り、保存値を変換しない', async () => {
  const signal = new AbortController().signal
  expect(await readPreparingGame(id, signal)).toEqual(game)
  expect(fetch).toHaveBeenLastCalledWith(
    `/api/games/${id}`,
    expect.objectContaining({
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
      signal,
    }),
  )
  body = { items: [game], next_cursor: 'opaque/+=' }
  expect(await listPreparingGames('previous/+==', signal)).toEqual(body)
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/games?limit=20&cursor=previous%2F%2B%3D%3D',
    expect.objectContaining({ method: 'GET', signal }),
  )
})
it('初期cursorはqueryへ入れず不正IDは通信前に拒否する', async () => {
  body = { items: [], next_cursor: null }
  await listPreparingGames(null)
  expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/games?limit=20')
  await expect(readPreparingGame('../other')).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([
  { status: 'finished' },
  { id: tenant },
  { scheduled_at: '2026-10-24T10:00:00' },
  { tournament_key: '' },
  { plate_umpire: 1 },
  { applied_rules: [] },
  { game_type_key: 'unknown' },
  { home_team_record_id: 'unknown' },
])('詳細のtransport不正を拒否: %j', async (patch) => {
  body = { ...game, ...patch }
  await expect(readPreparingGame(id)).rejects.toThrow()
})
it.each([
  null,
  {},
  { items: [], next_cursor: '' },
  { items: [game, { ...game, status: 'finished' }], next_cursor: null },
  { items: Array(21).fill(game), next_cursor: null },
])('一覧transport不正を拒否: %j', async (value) => {
  body = value
  await expect(listPreparingGames(null)).rejects.toThrow()
})
it('C2 metadata欠落を正常bodyでも採用しない', async () => {
  vi.mocked(fetch).mockResolvedValue(
    new Response(JSON.stringify(game), {
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  await expect(readPreparingGame(id)).rejects.toThrow()
  expect(useAuthStore().isAuthenticated).toBe(false)
})

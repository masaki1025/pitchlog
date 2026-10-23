import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import {
  createPreparingGame,
  readPreparationOptions,
  listPreparingGames,
  readPreparingGame,
  type PreparingGameCreate,
} from './games'
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

it.each(['list', 'detail'] as const)(
  '%sは既知語彙と同じ文字列表現のJSON配列を不正transportとして拒否する',
  async (endpoint) => {
    const invalid = { ...game, game_type_key: ['game_open'] }
    body =
      endpoint === 'list' ? { items: [invalid], next_cursor: null } : invalid
    await expect(
      endpoint === 'list' ? listPreparingGames(null) : readPreparingGame(id),
    ).rejects.toThrow(
      endpoint === 'list'
        ? '準備中一覧の応答が不正です'
        : '準備中詳細の応答が不正です',
    )
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(useAuthStore().isAuthenticated).toBe(true)
  },
)

const options = {
  game_types: [
    'game_official',
    'game_semi_official',
    'game_open',
    'game_intrasquad',
    'game_other',
  ].map((key) => ({ key, display_name: `<b>${key}</b>` })),
  tournaments: {
    items: [{ key: 'opaque', display_name: '<img src=x>' }],
    next_cursor: 'opaque/+=',
  },
}
const createBody: PreparingGameCreate = {
  scheduled_at: game.scheduled_at,
  game_type_key: 'game_open',
  away_team_record_id: tenant,
  home_team_record_id: id,
  tournament: { kind: 'new', display_name: ' 大会　' },
  plate_umpire: null,
  section_label: game.section_label,
  week_label: null,
  day_label: null,
  game_number_label: null,
}
it('作成選択肢GETとPOSTを既存clientのCookie/C2/signalで一度だけ送る', async () => {
  body = options
  const signal = new AbortController().signal
  expect(await readPreparationOptions('previous/+==', signal)).toEqual(options)
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/games/preparation-options?limit=20&cursor=previous%2F%2B%3D%3D',
    expect.objectContaining({ method: 'GET', credentials: 'include', signal }),
  )
  body = game
  expect(await createPreparingGame(createBody, signal)).toEqual(game)
  expect(fetch).toHaveBeenLastCalledWith(
    '/api/games',
    expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      signal,
      body: JSON.stringify(createBody),
    }),
  )
  expect(fetch).toHaveBeenCalledTimes(2)
})
it.each([
  {},
  { ...options, game_types: options.game_types.slice(1) },
  {
    ...options,
    game_types: options.game_types.map(() => options.game_types[0]),
  },
  {
    ...options,
    tournaments: {
      items: Array(21).fill({ key: 'x', display_name: 'x' }),
      next_cursor: null,
    },
  },
  {
    ...options,
    tournaments: {
      items: [
        { key: 'x', display_name: 'x' },
        { key: 'x', display_name: 'x' },
      ],
      next_cursor: null,
    },
  },
  { ...options, tournaments: { items: [], next_cursor: '' } },
])('選択肢transport不正は有効な作成供給にしない: %j', async (invalid) => {
  body = invalid
  await expect(readPreparationOptions(null)).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([
  { game_type_key: 'game_other' },
  { away_team_record_id: id },
  { section_label: 'changed' },
  { status: 'in_progress' },
])('POST結果の不正/入力不一致を作成済みへ採用しない: %j', async (patch) => {
  body = { ...game, ...patch }
  await expect(createPreparingGame(createBody)).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(1)
})

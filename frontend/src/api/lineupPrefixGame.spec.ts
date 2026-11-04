import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import fixture from './fixtures/lineupPrefixGame.v3.json'
import recordedFixture from './fixtures/lineupPrefixGame.recorded.v3.json'
import { isLineupPrefixGame, readLineupPrefixGame } from './lineupPrefixGame'
import { setVerifiedAuthForTest } from './auth.test-support'
import { useAuthStore } from '../stores/authStore'
let pinia: Pinia,
  body: unknown,
  status = 200
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: fixture.value.prefix_ref.tenantId,
    teamName: '構造fixture',
  })
  body = structuredClone(fixture.value)
  status = 200
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (_url, init) =>
        new Response(JSON.stringify(body), {
          status,
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
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('明示した新projectionのtenant/game・有界pageと全fieldを保持する', async () => {
  expect(isLineupPrefixGame(fixture.value)).toBe(true)
  expect(await readLineupPrefixGame(fixture.value.id)).toEqual({
    kind: 'found',
    game: fixture.value,
  })
  expect(String(vi.mocked(fetch).mock.calls[0]![0])).toContain(
    'projection=play-prefix-v3',
  )
})
it.each([
  'missing',
  'extra',
  'legacy',
  'scope',
  'cursor',
  'participant',
  'roster',
  'anchor',
  'page',
  'game',
  'rules',
])('不正%sを旧成功へfallbackせず拒否する', async (mutation) => {
  const v = JSON.parse(JSON.stringify(fixture.value))
  if (mutation === 'missing') delete v.after.battingOrderBySide
  if (mutation === 'extra') v.unknown = true
  if (mutation === 'legacy') v.read_kind = 'play-prefix'
  if (mutation === 'scope') v.prefix_ref.scope = 'play-prefix-v2'
  if (mutation === 'cursor') v.after.battingOrderBySide.home = '0'
  if (mutation === 'participant') delete v.participants.catcherId
  if (mutation === 'roster') v.lineup.home.pitcherId = v.lineup.away.pitcherId
  if (mutation === 'anchor')
    v.checkpoint_anchor = { id: v.id, revision: '1', history_version: '1' }
  if (mutation === 'page') v.page.next_cursor = 'cursor-without-row'
  if (mutation === 'game') v.prefix_ref.gameId = v.prefix_ref.tenantId
  if (mutation === 'rules') v.rules.regulationInnings = '9'
  body = v
  expect(isLineupPrefixGame(v)).toBe(false)
  await expect(readLineupPrefixGame(fixture.value.id)).rejects.toThrow()
  expect(fetch).toHaveBeenCalledTimes(1)
})
it.each([404, 409, 422, 503])(
  'HTTP %sを別projectionへ切り替えない',
  async (code) => {
    status = code
    if (code === 503)
      await expect(readLineupPrefixGame(fixture.value.id)).rejects.toThrow()
    else
      expect((await readLineupPrefixGame(fixture.value.id)).kind).not.toBe(
        'found',
      )
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)
it.each([0, 101, 1.5])('不正page上限%sは送らない', async (limit) => {
  await expect(
    readLineupPrefixGame(fixture.value.id, null, limit),
  ).rejects.toThrow()
  expect(fetch).not.toHaveBeenCalled()
})

it('実画面GETの保存headと開始原本anchorを混同せず復元する', async () => {
  const value = structuredClone(recordedFixture.value)
  expect(value.prefix_ref.checkpoint.id).not.toBe(value.checkpoint_anchor.id)
  expect(value.checkpoint_anchor.id).toBe(value.prefix_ref.origin.eventId)
  expect(isLineupPrefixGame(value)).toBe(true)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: value.prefix_ref.tenantId,
    teamName: '隔離実GET',
  })
  body = value
  expect(await readLineupPrefixGame(value.id)).toEqual({
    kind: 'found',
    game: value,
  })
})
it.each(['logical-id', 'storage-id', 'revision', 'history', 'storage-history'])(
  '保存headの%s不一致を表示成功へ上げない',
  async (field) => {
    const v = structuredClone(recordedFixture.value)
    if (field === 'logical-id')
      v.checkpoint_anchor.id = v.prefix_ref.checkpoint.id
    if (field === 'storage-id') v.storage_anchor.id = v.prefix_ref.checkpoint.id
    if (field === 'revision') v.checkpoint_anchor.revision = '999'
    if (field === 'history') v.checkpoint_anchor.history_version = '999'
    if (field === 'storage-history') v.storage_anchor.history_epoch = '999'
    expect(isLineupPrefixGame(v)).toBe(false)
    body = v
    await expect(readLineupPrefixGame(v.id)).rejects.toThrow()
    expect(fetch).toHaveBeenCalledTimes(1)
  },
)

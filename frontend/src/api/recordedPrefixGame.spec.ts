import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import { setVerifiedAuthForTest } from './auth.test-support'
import { useAuthStore } from '../stores/authStore'
import {
  isRecordedPrefixGame,
  ordinaryContextFromRead,
  readRecordedPrefixGame,
} from './recordedPrefixGame'
const fixtures = JSON.parse(
  readFileSync(
    resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
    'utf8',
  ),
).positive
let pinia: Pinia
let body: unknown
let responseStatus = 200
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: fixtures[0].value.prefix_ref.tenantId,
    teamName: 'A',
  })
  body = fixtures[0].value
  responseStatus = 200
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async (_url, init) =>
        new Response(JSON.stringify(body), {
          status: responseStatus,
          headers: {
            'Content-Type': 'application/json',
            ...(responseStatus === 200
              ? {
                  'X-Pitchlog-Tenant-Match': '1',
                  'X-Pitchlog-Tenant-Challenge': new Headers(init?.headers).get(
                    'X-Pitchlog-Tenant-Challenge',
                  )!,
                }
              : {}),
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
it('n0/新1/旧1/実checkpoint2の全公開列を保持して読み、初期stateと現在afterを区別する', () => {
  expect(fixtures).toHaveLength(4)
  for (const row of fixtures) {
    expect(isRecordedPrefixGame(row.value), row.id).toBe(true)
    const context = ordinaryContextFromRead(
      row.value,
      row.value.prefix_ref.tenantId,
    )
    expect(context.after).toEqual(row.value.after)
    expect(context.game.state).toEqual(row.value.state)
    expect(context.nextPosition).toEqual(row.value.next_position)
    expect(context.source).toBe('server-confirmed')
    expect(context.nextPosition.d2).not.toBe(context.prefixRef.length)
  }
})
it('checkpoint生成をGETの見かけにせず、欠落列/別game/過大page/補修値を閉拒否する', () => {
  const invalid: unknown[] = []
  const zero = structuredClone(fixtures[0].value)
  zero.checkpoint_anchor = { id: zero.id, revision: '1', history_version: '1' }
  invalid.push(zero)
  const lost = structuredClone(fixtures[2].value)
  lost.checkpoint_anchor = null
  invalid.push(lost)
  const omitted = structuredClone(fixtures[2].value)
  delete omitted.page.items[0].play_row.stance
  invalid.push(omitted)
  const crossed = structuredClone(fixtures[2].value)
  crossed.page.items[0].play_row.game_id =
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  invalid.push(crossed)
  const extra = structuredClone(fixtures[2].value)
  extra.history = []
  invalid.push(extra)
  const many = structuredClone(fixtures[2].value)
  many.page.items = Array(101).fill(many.page.items[0])
  invalid.push(many)
  for (const [path, key] of [
    ['next_position', 'd2'],
    ['checkpoint_anchor', 'revision'],
  ] as const) {
    const v = structuredClone(fixtures[2].value)
    v[path][key] = '01'
    invalid.push(v)
  }
  const noTimestamp = structuredClone(fixtures[0].value)
  delete noTimestamp.last_saved_at
  invalid.push(noTimestamp)
  const inventedInitialTimestamp = structuredClone(fixtures[0].value)
  inventedInitialTimestamp.last_saved_at = '2026-10-30T09:00:00Z'
  invalid.push(inventedInitialTimestamp)
  const wrongPolicy = structuredClone(fixtures[0].value)
  wrongPolicy.append_policy.max_d2 = '9223372036854775807'
  invalid.push(wrongPolicy)
  for (const v of invalid) expect(isRecordedPrefixGame(v)).toBe(false)
  expect(() =>
    ordinaryContextFromRead(
      fixtures[2].value,
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    ),
  ).toThrow()
})
it('明示projection/tenantBound/finite queryを送り、無query旧routeの契約を変えない', async () => {
  const value = fixtures[2].value
  body = value
  expect(await readRecordedPrefixGame(value.id)).toEqual({
    kind: 'found',
    game: value,
  })
  const [url, init] = vi.mocked(fetch).mock.calls[0]!
  expect(String(url)).toBe(
    `/api/games/${value.id}/started?projection=ordinary-prefix-v1&limit=25`,
  )
  expect(init?.credentials).toBe('include')
  expect(
    new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge'),
  ).toBeTruthy()
})
it('未提供/409/404を成功と表示せず、未知/不正応答を捨てる', async () => {
  const value = structuredClone(fixtures[0].value)
  body = { ...value, unexpected: true }
  await expect(readRecordedPrefixGame(value.id)).rejects.toThrow()
  for (const [status, kind] of [
    [404, 'not-found'],
    [409, 'unavailable'],
    [501, 'unsupported'],
  ] as const) {
    responseStatus = status
    body = { error: { message: 'unavailable', fields: [] } }
    expect(await readRecordedPrefixGame(value.id)).toEqual({ kind })
  }
})

import { isPlayPrefixGame, readPlayPrefixGame } from './recordedPrefixGame'
function playInitial() {
  const old = structuredClone(fixtures[0].value)
  return {
    ...old,
    read_kind: 'play-prefix',
    last_source: null,
    prior_artifact_sha256: 'a'.repeat(64),
    pa_start_source: { kind: 'started-game', id: old.id },
    bridge_checkpoint: {
      id: '10000000-0000-4000-8000-000000000099',
      revision: '1',
      digest: 'a'.repeat(64),
    },
    storage_anchor: null,
    bridge_origin: null,
    runners: [],
    participants: null,
  }
}
it('新v2初期GETを閉検証し旧DTOの成功や欠落sourceへ置換しない', async () => {
  body = playInitial()
  expect(isPlayPrefixGame(body)).toBe(true)
  expect((await readPlayPrefixGame(fixtures[0].value.id)).kind).toBe('found')
  expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toContain(
    'projection=play-prefix-v2',
  )
  for (const change of [
    { bridge_checkpoint: null },
    {
      storage_anchor: {
        id: '10000000-0000-4000-8000-000000000099',
        history_epoch: '1',
      },
    },
    { last_source: { eventId: 'bad', d5: 'bad', playId: 'bad' } },
    { unknown: true },
  ])
    expect(isPlayPrefixGame({ ...playInitial(), ...change })).toBe(false)
  body = fixtures[0].value
  await expect(readPlayPrefixGame(fixtures[0].value.id)).rejects.toThrow()
})

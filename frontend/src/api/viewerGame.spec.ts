import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import initial from './fixtures/lineupPrefixGame.v3.json'
import recorded from './fixtures/lineupPrefixGame.recorded.v3.json'
import { setVerifiedAuthForTest } from './auth.test-support'
import { useAuthStore } from '../stores/authStore'
import { readViewerGame, readViewerHead, type ViewerHead } from './viewerGame'

let pinia: Pinia
let payload: unknown
let status: number
const tenant = initial.value.prefix_ref.tenantId
const gameId = initial.value.id
const head: ViewerHead = {
  status: 'in_progress',
  generation: '1',
  watermark: initial.value.prefix_ref.length,
}
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: '閲覧fixture' })
  payload = structuredClone(initial.value)
  status = 200
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, init) =>
      new Response(JSON.stringify(payload), {
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
it('表示本体は専用RR routeだけを呼び、保存済み0球を受理する', async () => {
  expect(await readViewerGame(gameId, tenant, head)).toEqual(initial.value)
  expect(String(vi.mocked(fetch).mock.calls[0]![0])).toBe(
    `/api/games/${gameId}/viewer?limit=25`,
  )
})
it('保存球の実watermarkを照合し、probeだけで表示成功にしない', async () => {
  payload = structuredClone(recorded.value)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: recorded.value.prefix_ref.tenantId,
    teamName: '保存球fixture',
  })
  const target = recorded.value.id
  const owner = recorded.value.prefix_ref.tenantId
  await expect(readViewerGame(target, owner, head)).rejects.toThrow()
  const current = { ...head, watermark: recorded.value.prefix_ref.length }
  expect(await readViewerGame(target, owner, current)).toEqual(recorded.value)
})
it('終了済みlineupの保存済み全項目を閉検査し、未知keyを拒否する', async () => {
  payload = { ...structuredClone(recorded.value), status: 'finished' }
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: recorded.value.prefix_ref.tenantId,
    teamName: '終了済みfixture',
  })
  const finishedHead = {
    ...head,
    status: 'finished' as const,
    watermark: recorded.value.prefix_ref.length,
  }
  const target = recorded.value.id
  const owner = recorded.value.prefix_ref.tenantId
  expect(await readViewerGame(target, owner, finishedHead)).toEqual(payload)
  payload = { ...(payload as Record<string, unknown>), unknown: true }
  await expect(readViewerGame(target, owner, finishedHead)).rejects.toThrow()
})
it('別tenant、別game、未知key、破損履歴を拒否する', async () => {
  const other = '33333333-3333-4333-8333-333333333333'
  await expect(readViewerGame(gameId, other, head)).rejects.toThrow()
  const wrong = structuredClone(initial.value) as Record<string, unknown>
  wrong.unknown = true
  payload = wrong
  await expect(readViewerGame(gameId, tenant, head)).rejects.toThrow()
})
it('headは閉3値のみを採用し、HTTP失敗時は古い値を返さない', async () => {
  payload = head
  expect(await readViewerHead(gameId)).toEqual(head)
  payload = { ...head, unknown: true }
  await expect(readViewerHead(gameId)).rejects.toThrow()
  status = 503
  await expect(readViewerHead(gameId)).rejects.toThrow()
})

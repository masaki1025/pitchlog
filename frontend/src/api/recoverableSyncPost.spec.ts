import { IDBFactory } from 'fake-indexeddb'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import {
  postRecoverableP3Change,
  postRecoverableSyncRequest,
} from './recoverableSyncPost'
import { SyncAttemptBarrier } from '../lib/syncAttemptBarrier'

const tenant = '00000000-0000-4000-8000-000000000011'
const game = '00000000-0000-4000-8000-000000000012'
const device = '00000000-0000-4000-8000-000000000013'
const attempt = '00000000-0000-4000-8000-000000000014'
const credentials = {
  deviceId: device,
  deviceCredential: 'public-test-value',
  attempt,
}
function body() {
  return {
    recovery_generation: '1',
    recording_right_proof: 'original-proof',
    change: {
      d5: '00000000-0000-4000-8000-000000000015',
      game_id: game,
      event_kind: 'play_change',
      target_reference: { game, d4: 'D4', d1: 1 },
      expected_version: 1,
      payload: { observed: 'original' },
    },
  }
}
let pinia: Pinia
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: tenant,
    teamName: 'HTTP-double-only',
  })
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => {
  vi.unstubAllGlobals()
  disposePinia(pinia)
})
function response(init: RequestInit | undefined, value: unknown) {
  const challenge = new Headers(init?.headers).get(
    'X-Pitchlog-Tenant-Challenge',
  )
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      ...(challenge === null
        ? {}
        : {
            'X-Pitchlog-Tenant-Match': '1',
            'X-Pitchlog-Tenant-Challenge': challenge,
          }),
    },
  })
}
it('P3は元本文の照会後だけ新attemptで同D5/changeへ再送する', async () => {
  const sent: { url: string; init: RequestInit | undefined }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      sent.push({ url, init })
      return response(
        init,
        url.endsWith('/attempts/recover')
          ? { resolution: 'retry_allowed' }
          : { testOnly: 'not-a-product-ack' },
      )
    }),
  )
  const original = body()
  await postRecoverableP3Change(game, original, credentials)
  await postRecoverableP3Change(game, original, credentials)
  expect(sent.map((x) => x.url)).toEqual([
    `/api/games/${game}/sync/change`,
    `/api/games/${game}/sync/attempts/recover`,
    `/api/games/${game}/sync/change`,
  ])
  for (const request of sent)
    expect(JSON.parse(String(request.init?.body))).toEqual(original)
  const attempts = sent.map((x) =>
    new Headers(x.init?.headers).get('X-Pitchlog-Sync-Attempt'),
  )
  expect(attempts[0]).toBe(attempt)
  expect(attempts[1]).toBe(attempt)
  expect(attempts[2]).not.toBe(attempt)
  expect(attempts[2]).toMatch(/^[a-f0-9-]{36}$/)
})
it('unresolvedでchangeを再送せず、新attempt/成功を作らない', async () => {
  const sent: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      sent.push(url)
      return response(
        init,
        url.endsWith('/attempts/recover')
          ? { resolution: 'unresolved' }
          : { testOnly: 'not-a-product-ack' },
      )
    }),
  )
  await postRecoverableP3Change(game, body(), credentials)
  await expect(
    postRecoverableP3Change(game, body(), credentials),
  ).rejects.toThrow()
  expect(sent).toHaveLength(2)
  expect(sent[1]).toBe(`/api/games/${game}/sync/attempts/recover`)
})
it('P3原本文を旧events入口へ送信しない', async () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  await expect(
    postRecoverableSyncRequest(game, body(), credentials),
  ).rejects.toThrow()
  expect(fetcher).not.toHaveBeenCalled()
})

it('照会済みの本文は再照会せず、固定した次attemptで送る', async () => {
  const d5 = '00000000-0000-4000-8000-000000000015'
  const original = {
    recording_right_proof: 'original-proof',
    events: [
      {
        d5,
        d1: 1,
        d4: 'D4',
        game_id: game,
        event_kind: 'play',
        payload: { observed: 'original' },
      },
    ],
  }
  const sent: { url: string; attempt: string | null }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      sent.push({
        url,
        attempt: new Headers(init?.headers).get('X-Pitchlog-Sync-Attempt'),
      })
      return response(init, { testOnly: 'not-a-product-ack' })
    }),
  )
  await postRecoverableSyncRequest(game, original, credentials)
  expect(sent).toEqual([{ url: `/api/games/${game}/sync/events`, attempt }])
  const barrier = await SyncAttemptBarrier.open()
  const next = '00000000-0000-4000-8000-000000000099'
  try {
    const prepared = await barrier.prepare(
      tenant,
      game,
      original,
      device,
      attempt,
    )
    await barrier.advance(prepared.barrier, next)
  } finally {
    barrier.close()
  }
  sent.length = 0
  await postRecoverableSyncRequest(game, original, credentials, {
    skipRecovery: true,
  })
  expect(sent).toEqual([
    { url: `/api/games/${game}/sync/events`, attempt: next },
  ])
})

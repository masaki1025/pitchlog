import { setVerifiedAuthForTest } from './auth.test-support'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/authStore'
import { queryClient } from '../lib/queryClient'
import {
  ApiSessionUnverifiedError,
  ApiTenantVerificationError,
  apiRequest,
} from './client'

const TENANT_A = '11111111-1111-1111-1111-111111111111'
const TENANT_B = '22222222-2222-2222-2222-222222222222'
let pinia: Pinia
function signIn(teamId = TENANT_A) {
  setVerifiedAuthForTest(useAuthStore(), {
    teamId,
    teamName: '検証済み試験チーム',
  })
}
function response(challenge: string, ack = '1', status = 200) {
  return new Response('{"items":[]}', {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Pitchlog-Tenant-Match': ack,
      'X-Pitchlog-Tenant-Challenge': challenge,
    },
  })
}
function echoResponse(_url: unknown, init?: RequestInit) {
  return Promise.resolve(
    response(new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!),
  )
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  signIn()
  vi.stubGlobal('fetch', vi.fn(echoResponse))
})
afterEach(() => {
  queryClient.clear()
  disposePinia(pinia)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
describe('tenant-boundの共通client境界', () => {
  it('要求ごとにchallengeを生成しtenantと共に送り、2xxのexact echoだけ返す', async () => {
    await expect(
      apiRequest('GET', '/players', { tenantBound: true }),
    ).resolves.toEqual({ items: [] })
    await apiRequest('GET', '/players', { tenantBound: true })
    const headers = vi
      .mocked(fetch)
      .mock.calls.map(([, init]) => new Headers(init?.headers))
    expect(headers[0]!.get('X-Pitchlog-Expected-Tenant')).toBe(TENANT_A)
    expect(headers[0]!.get('X-Pitchlog-Tenant-Challenge')).not.toBe(
      headers[1]!.get('X-Pitchlog-Tenant-Challenge'),
    )
    expect(headers[0]!.get('X-Pitchlog-Tenant-Challenge')).toMatch(
      /^[0-9a-f-]{36}$/,
    )
  })
  it.each([
    '',
    'TEAM-A',
    'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA',
    '11111111111111111111111111111111',
  ])('非canonical tenant %s はfetch前に拒否する', async (tenant) => {
    signIn()
    useAuthStore().teamId = tenant
    await expect(
      apiRequest('GET', '/players', { tenantBound: true }),
    ).rejects.toBeInstanceOf(ApiSessionUnverifiedError)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('未確認sessionでは通信しない', async () => {
    useAuthStore().signOut()
    await expect(
      apiRequest('GET', '/players', { tenantBound: true }),
    ).rejects.toBeInstanceOf(ApiSessionUnverifiedError)
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each([null, '', '0', '1, 1', 'true'])(
    '2xx ack %s は本文を読む前に拒否する',
    async (ack) => {
      queryClient.setQueryData(['private'], '旧cache')
      let read!: ReturnType<typeof vi.spyOn>
      vi.mocked(fetch).mockImplementation(async (_url, init) => {
        const challenge = new Headers(init?.headers).get(
          'X-Pitchlog-Tenant-Challenge',
        )!
        const res = response(challenge)
        if (ack === null) res.headers.delete('X-Pitchlog-Tenant-Match')
        else res.headers.set('X-Pitchlog-Tenant-Match', ack)
        read = vi.spyOn(res, 'text')
        return res
      })
      await expect(
        apiRequest('POST', '/players', { tenantBound: true, body: {} }),
      ).rejects.toBeInstanceOf(ApiTenantVerificationError)
      expect(read).not.toHaveBeenCalled()
      expect(fetch).toHaveBeenCalledTimes(1)
      expect(useAuthStore().isAuthenticated).toBe(false)
      expect(queryClient.getQueryCache().getAll()).toEqual([])
      await expect(
        apiRequest('GET', '/players', { tenantBound: true }),
      ).rejects.toBeInstanceOf(ApiSessionUnverifiedError)
      expect(fetch).toHaveBeenCalledTimes(1)
    },
  )
  it.each([null, '', TENANT_A, `${TENANT_A}, ${TENANT_B}`])(
    'challenge %s の欠落・別値・複数値を拒否する',
    async (challenge) => {
      const res = response(challenge ?? '')
      if (challenge === null) res.headers.delete('X-Pitchlog-Tenant-Challenge')
      const read = vi.spyOn(res, 'text')
      vi.mocked(fetch).mockResolvedValue(res)
      await expect(
        apiRequest('GET', '/players', { tenantBound: true }),
      ).rejects.toBeInstanceOf(ApiTenantVerificationError)
      expect(read).not.toHaveBeenCalled()
      expect(useAuthStore().isAuthenticated).toBe(false)
      expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
    },
  )
  it('Aの過去2xxをB要求へ注入しても本文を採用しない', async () => {
    let oldChallenge = ''
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => {
      oldChallenge = new Headers(init?.headers).get(
        'X-Pitchlog-Tenant-Challenge',
      )!
      return response(oldChallenge)
    })
    await apiRequest('GET', '/players', { tenantBound: true })
    signIn(TENANT_B)
    const oldResponse = response(oldChallenge)
    const read = vi.spyOn(oldResponse, 'text')
    vi.mocked(fetch).mockResolvedValueOnce(oldResponse)
    await expect(
      apiRequest('GET', '/players', { tenantBound: true }),
    ).rejects.toBeInstanceOf(ApiTenantVerificationError)
    expect(read).not.toHaveBeenCalled()
    expect(useAuthStore().isAuthenticated).toBe(false)
  })
  it.each(['GET', 'POST'] as const)(
    '%sの遅延headersは認証切替後に本文を読まず拒否する',
    async (method) => {
      const pending = deferred<Response>()
      vi.mocked(fetch).mockReturnValueOnce(pending.promise)
      const result = apiRequest(method, '/players', { tenantBound: true })
      signIn(TENANT_B)
      queryClient.setQueryData(['new-tenant'], '維持')
      const res = response(
        new Headers(vi.mocked(fetch).mock.calls[0]![1]?.headers).get(
          'X-Pitchlog-Tenant-Challenge',
        )!,
      )
      const read = vi.spyOn(res, 'text')
      pending.resolve(res)
      await expect(result).rejects.toBeInstanceOf(ApiTenantVerificationError)
      expect(read).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(['new-tenant'])).toBeUndefined()
      expect(useAuthStore().isAuthenticated).toBe(false)
    },
  )
  it('本文読取中の世代切替でも応答を採用しない', async () => {
    const pending = deferred<string>()
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => {
      const res = response(
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!,
      )
      vi.spyOn(res, 'text').mockImplementation(() => {
        signIn(TENANT_B)
        return pending.promise
      })
      return res
    })
    const result = apiRequest('PATCH', '/players/id', { tenantBound: true })
    await vi.waitFor(() => expect(useAuthStore().teamId).toBe(TENANT_B))
    pending.resolve('{"name":"old"}')
    await expect(result).rejects.toBeInstanceOf(ApiTenantVerificationError)
  })
  it('teamId改変をstorage同期で検出する', async () => {
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => {
      useAuthStore().teamId = TENANT_B
      return response(
        new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!,
      )
    })
    await expect(
      apiRequest('GET', '/players', { tenantBound: true }),
    ).rejects.toBeInstanceOf(ApiTenantVerificationError)
  })
  it.each([401, 404, 409, 422, 500])(
    '非2xx %s にackを要求せず既存status処理へ渡す',
    async (status) => {
      vi.mocked(fetch).mockResolvedValue(new Response('{}', { status }))
      await expect(
        apiRequest('POST', '/players', { tenantBound: true }),
      ).rejects.toMatchObject({ status, name: 'ApiError' })
      if (status === 401) expect(useAuthStore().isAuthenticated).toBe(false)
    },
  )
  it('古い401は新しいsessionを失効させない', async () => {
    const pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    const result = apiRequest('GET', '/players', { tenantBound: true })
    signIn(TENANT_B)
    pending.resolve(new Response('{}', { status: 401 }))
    await expect(result).rejects.toBeInstanceOf(ApiTenantVerificationError)
    expect(useAuthStore().teamId).toBe(TENANT_B)
    expect(useAuthStore().isAuthenticated).toBe(true)
  })
  it('非tenant要求はmetadataを送らずackを必要としない', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('{}', { headers: { 'Content-Type': 'application/json' } }),
    )
    await apiRequest('GET', '/auth/session')
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]![1]?.headers)
    expect(headers.has('X-Pitchlog-Expected-Tenant')).toBe(false)
    expect(headers.has('X-Pitchlog-Tenant-Challenge')).toBe(false)
  })
})

it('lock競合中のmetadata不正も通知し、変更要求を再送しない', async () => {
  queryClient.setQueryData(['private'], '旧cache')
  vi.stubGlobal('navigator', {
    locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
  })
  vi.mocked(fetch).mockResolvedValue(response('wrong'))
  await expect(
    apiRequest('POST', '/players', { tenantBound: true, body: {} }),
  ).rejects.toBeInstanceOf(ApiTenantVerificationError)
  expect(useAuthStore().isAuthenticated).toBe(false)
  expect(queryClient.getQueryCache().getAll()).toEqual([])
  expect(localStorage.getItem('bb.auth.uncertain')).not.toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('正しいmetadataのJSON不正を認証未確認へ一律変換しない', async () => {
  queryClient.setQueryData(['private'], '正規cache')
  vi.mocked(fetch).mockImplementation(async (_url, init) => {
    const res = response(
      new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!,
    )
    vi.spyOn(res, 'text').mockResolvedValue('{')
    return res
  })
  await expect(
    apiRequest('POST', '/players', { tenantBound: true, body: {} }),
  ).rejects.toMatchObject({ name: 'ApiError' })
  expect(useAuthStore().isAuthenticated).toBe(true)
  expect(queryClient.getQueryData(['private'])).toBe('正規cache')
  expect(localStorage.getItem('bb.auth.uncertain')).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('storage同期とは独立にteamId不一致を本文前に拒否する', async () => {
  const auth = useAuthStore()
  const epoch = auth.authEpoch
  vi.mocked(fetch).mockImplementationOnce(async (_url, init) => {
    vi.spyOn(auth, 'syncFromStorage').mockImplementation(() => {})
    auth.teamId = TENANT_B
    return response(
      new Headers(init?.headers).get('X-Pitchlog-Tenant-Challenge')!,
    )
  })
  await expect(
    apiRequest('GET', '/players', { tenantBound: true }),
  ).rejects.toBeInstanceOf(ApiTenantVerificationError)
  expect(auth.authEpoch).toBe(epoch)
  expect(fetch).toHaveBeenCalledTimes(1)
})

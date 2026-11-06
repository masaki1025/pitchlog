import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/authStore'
import { setVerifiedAuthForTest } from './auth.test-support'
import { downloadPlayCsv } from './gameExports'

let pinia: Pinia
const TENANT = '6efca380-dea3-5a4e-9749-40dfb1dbd65e'
beforeEach(() => {
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamName: '試験', teamId: TENANT })
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  disposePinia(pinia)
})

describe('毎球CSVの実client C2境界', () => {
  it('期待tenantと要求固有challengeを送り、同じchallenge応答だけを読む', async () => {
    vi.mocked(fetch).mockImplementation(async (_url, init) => {
      const headers = new Headers(init?.headers)
      expect(headers.get('X-Pitchlog-Expected-Tenant')).toBe(TENANT)
      const challenge = headers.get('X-Pitchlog-Tenant-Challenge')
      expect(challenge).toMatch(/^[a-f0-9-]{36}$/)
      return new Response('zipdata', {
        headers: {
          'X-Pitchlog-Tenant-Match': '1',
          'X-Pitchlog-Tenant-Challenge': challenge!,
          'Content-Length': '7',
          'X-Pitchlog-Archive-SHA256':
            'a1b8b2250981a957cb59f74e9a9eb9f019e94e7e50d28596f6a927112b1ca256',
        },
      })
    })
    const result = await downloadPlayCsv('game-1')
    expect(await result.blob.text()).toBe('zipdata')
    expect(result.contentLength).toBe(7)
    expect(fetch).toHaveBeenCalledWith(
      '/api/games/game-1/exports/plays.zip',
      expect.objectContaining({ cache: 'no-store', credentials: 'include' }),
    )
  })

  it.each(['missing', 'wrong-challenge'])(
    'C2 %s応答をBlobとして消費しない',
    async (mode) => {
      const response = new Response('zipdata', {
        headers:
          mode === 'missing'
            ? {}
            : {
                'X-Pitchlog-Tenant-Match': '1',
                'X-Pitchlog-Tenant-Challenge':
                  'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
              },
      })
      const blob = vi.spyOn(response, 'blob')
      vi.mocked(fetch).mockResolvedValue(response)
      await expect(downloadPlayCsv('game-1')).rejects.toMatchObject({
        name: 'ApiTenantVerificationError',
      })
      expect(blob).not.toHaveBeenCalled()
    },
  )
})

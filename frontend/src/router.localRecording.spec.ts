import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { pinia } from './appProviders'
import { useAuthStore } from './stores/authStore'
import * as authApi from './api/auth'
import * as local from './lib/localRecordingSession'
import { createAppRouter } from './router'

// guardの分岐検査。保存資格の真正性は別の実IDB/controller試験で照合する。
const game = '59c28087-e5d8-43e1-9e50-65833ad0cae6'
function saved() {
  return {
    current: true,
    dispose: vi.fn(),
  } as unknown as local.LocalRecordingSession
}
beforeEach(() => {
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  auth.signOut()
  auth.hasHydrated = true
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
describe('断中の記録入口だけを端末内へ戻す', () => {
  it('真正保存scopeと不達の組合せだけで、HTTP認証未確認のまま記録入口へ入る', async () => {
    const scope = saved()
    vi.spyOn(local.LocalRecordingSession, 'restore').mockResolvedValue(scope)
    vi.spyOn(local, 'recordingBackendReachability').mockResolvedValue(
      'unavailable',
    )
    const verify = vi.spyOn(authApi, 'ensureSessionVerified')
    const router = createAppRouter(createMemoryHistory())
    await router.push(`/games/${game}/record`)
    expect(router.currentRoute.value.name).toBe('game-record')
    expect(verify).not.toHaveBeenCalled()
    expect(useAuthStore(pinia).isAuthenticated).toBe(false)
    await router.push('/help')
    expect(scope.dispose).toHaveBeenCalledOnce()
  })
  it.each(['available', 'unknown'] as const)(
    '%sなら既session拒否を迂回しない',
    async (availability) => {
      vi.spyOn(local.LocalRecordingSession, 'restore').mockResolvedValue(
        saved(),
      )
      vi.spyOn(local, 'recordingBackendReachability').mockResolvedValue(
        availability,
      )
      const verify = vi
        .spyOn(authApi, 'ensureSessionVerified')
        .mockRejectedValue(new Error('401'))
      const router = createAppRouter(createMemoryHistory())
      await router.push(`/games/${game}/record`)
      expect(verify).toHaveBeenCalledOnce()
      expect(router.currentRoute.value.name).toBe('login')
    },
  )
  it('保存原本が無ければ不達を代替認証にしない', async () => {
    vi.spyOn(local.LocalRecordingSession, 'restore').mockResolvedValue(null)
    const health = vi.spyOn(local, 'recordingBackendReachability')
    vi.spyOn(authApi, 'ensureSessionVerified').mockRejectedValue(
      new Error('network'),
    )
    const router = createAppRouter(createMemoryHistory())
    await router.push(`/games/${game}/record`)
    expect(health).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('login')
  })
  it('teamへ端末内scopeを流用しない', async () => {
    const restore = vi
      .spyOn(local.LocalRecordingSession, 'restore')
      .mockResolvedValue(saved())
    vi.spyOn(authApi, 'ensureSessionVerified').mockRejectedValue(
      new Error('network'),
    )
    const router = createAppRouter(createMemoryHistory())
    await router.push('/team')
    expect(restore).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('login')
  })
})

describe('public到達確認は認証の代替にしない', () => {
  it.each([
    [200, 'available'],
    [401, 'available'],
    [403, 'available'],
    [503, 'unavailable'],
    [302, 'unknown'],
  ] as const)(
    'HTTP %iの扱いを閉じ、Cookieを送信しない',
    async (status, expected) => {
      vi.stubGlobal('navigator', { onLine: true })
      const request = vi.fn().mockResolvedValue(new Response(null, { status }))
      vi.stubGlobal('fetch', request)
      expect(await local.recordingBackendReachability()).toBe(expected)
      expect(request).toHaveBeenCalledWith(
        '/api/health',
        expect.objectContaining({
          credentials: 'omit',
          redirect: 'manual',
          cache: 'no-store',
        }),
      )
    },
  )
  it('network TypeErrorだけを不達へ写す', async () => {
    vi.stubGlobal('navigator', { onLine: true })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')))
    expect(await local.recordingBackendReachability()).toBe('unavailable')
  })
  it('実装内部の未知例外を断中成功へ写さない', async () => {
    vi.stubGlobal('navigator', { onLine: true })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('internal')))
    expect(await local.recordingBackendReachability()).toBe('unknown')
  })
})

it('onLine=falseというhintだけで到達可能なhealthを省略しない', async () => {
  vi.stubGlobal('navigator', { onLine: false })
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
  vi.stubGlobal('fetch', fetcher)
  expect(await local.recordingBackendReachability()).toBe('available')
  expect(fetcher).toHaveBeenCalledOnce()
})

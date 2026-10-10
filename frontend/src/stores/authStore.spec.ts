import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from './authStore'

type StoredAuth = {
  version: number
  sessionId: string
  teamName: string
  teamId: string | null
}

function savedAuth(): StoredAuth {
  return JSON.parse(
    localStorage.getItem(AUTH_STORAGE_KEY) ?? '{}',
  ) as StoredAuth
}

function expectCacheReset(
  operation: (store: ReturnType<typeof useAuthStore>) => void,
): void {
  const store = useAuthStore()
  queryClient.setQueryData(['x'], 1)
  const previousEpoch = store.authEpoch

  operation(store)

  expect(queryClient.getQueryCache().getAll()).toEqual([])
  expect(store.authEpoch).toBe(previousEpoch + 1)
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  queryClient.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  queryClient.clear()
})

describe('authStore', () => {
  it('保存値がないとき未認証で同期的に復元を完了する', () => {
    const store = useAuthStore()

    expect(store.teamName).toBeNull()
    expect(store.teamId).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(store.sessionExpired).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(store.authEpoch).toBe(0)
  })

  it('signIn で認証済みとなり指定の4キーだけを保存する', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    expect(store.isAuthenticated).toBe(true)
    expect(store.teamName).toBe('チーム A')
    expect(store.teamId).toBe('team-a')
    expect('sessionId' in store).toBe(false)
    expect(Object.keys(savedAuth())).toEqual([
      'version',
      'sessionId',
      'teamName',
      'teamId',
    ])
    expect(savedAuth()).toEqual({
      version: 1,
      sessionId: expect.any(String),
      teamName: 'チーム A',
      teamId: 'team-a',
    })
    expect(savedAuth().sessionId).not.toBe('')
  })

  it('signIn のたびに異なる sessionId を保存する', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A' })
    const firstSessionId = savedAuth().sessionId

    store.signIn({ teamName: 'チーム A' })

    expect(savedAuth().sessionId).not.toBe(firstSessionId)
  })

  it('teamId を省略した signIn は null を保存する', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A' })

    expect(store.teamId).toBeNull()
    expect(savedAuth().teamId).toBeNull()
  })

  it('signOut は保存キーを消して未認証へ戻す', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    store.signOut()

    expect(store.isAuthenticated).toBe(false)
    expect(store.teamName).toBeNull()
    expect(store.teamId).toBeNull()
    expect(store.sessionExpired).toBe(false)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })

  it('expireSession は失効を示し、次の signIn で失効表示を下ろす', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    store.expireSession()

    expect(store.isAuthenticated).toBe(false)
    expect(store.teamName).toBeNull()
    expect(store.teamId).toBeNull()
    expect(store.sessionExpired).toBe(true)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()

    store.signIn({ teamName: 'チーム B' })
    expect(store.sessionExpired).toBe(false)
    expect(store.isAuthenticated).toBe(true)
  })

  it('signIn はキャッシュを消し authEpoch を増やす', () => {
    expectCacheReset((store) => store.signIn({ teamName: 'チーム A' }))
  })

  it('signOut はキャッシュを消し authEpoch を増やす', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A' })
    expectCacheReset((current) => current.signOut())
  })

  it('expireSession はキャッシュを消し authEpoch を増やす', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A' })
    expectCacheReset((current) => current.expireSession())
  })

  it('新しい Pinia では保存済みの同じチームを復元する', () => {
    const original = useAuthStore()
    original.signIn({ teamName: 'チーム A', teamId: 'team-a' })
    const sessionId = savedAuth().sessionId

    setActivePinia(createPinia())
    const restored = useAuthStore()

    expect(restored.isAuthenticated).toBe(true)
    expect(restored.teamName).toBe('チーム A')
    expect(restored.teamId).toBe('team-a')
    expect(restored.hasHydrated).toBe(true)
    expect(restored.authEpoch).toBe(0)
    expect(savedAuth().sessionId).toBe(sessionId)
  })

  it('JSON でない保存値は消して未認証で始める', () => {
    localStorage.setItem(AUTH_STORAGE_KEY, '{not json')

    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })

  it.each([
    ['版が違う', { version: 2, sessionId: 's', teamName: 'A', teamId: null }],
    [
      'sessionId が空',
      { version: 1, sessionId: '', teamName: 'A', teamId: null },
    ],
    [
      'teamName が空',
      { version: 1, sessionId: 's', teamName: '', teamId: null },
    ],
    [
      'teamId が文字列でも null でもない',
      { version: 1, sessionId: 's', teamName: 'A', teamId: 1 },
    ],
    [
      '余分なキーがある',
      { version: 1, sessionId: 's', teamName: 'A', teamId: null, extra: 1 },
    ],
    ['必須キーがない', { version: 1, sessionId: 's', teamName: 'A' }],
  ])('形が違う保存値（%s）は消して未認証で始める', (_name, value) => {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(value))

    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })

  it('旧 zustand 形式は消して未認証で始める', () => {
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({
        state: { token: 'secret-token', teamId: 1 },
        version: 0,
      }),
    )

    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })

  it('getItem が例外を投げても生成と3操作は止まらない', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('read failed')
    })
    const store = useAuthStore()

    expect(store.isAuthenticated).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(() => store.signIn({ teamName: 'チーム A' })).not.toThrow()
    expect(() => store.signOut()).not.toThrow()
    expect(() => store.expireSession()).not.toThrow()
  })

  it('setItem が例外を投げたら削除を試み、値を含まない警告を出す', () => {
    const sessionId = '11111111-1111-4111-8111-111111111111'
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(sessionId)
    const remove = vi.spyOn(Storage.prototype, 'removeItem')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('write failed')
    })
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = useAuthStore()

    expect(() =>
      store.signIn({ teamName: '機密チーム名', teamId: 'secret-team-id' }),
    ).not.toThrow()

    expect(store.isAuthenticated).toBe(true)
    expect(store.teamId).toBe('secret-team-id')
    expect(remove).toHaveBeenCalledWith(AUTH_STORAGE_KEY)
    expect(warning).toHaveBeenCalled()
    const warningText = JSON.stringify(warning.mock.calls)
    expect(warningText).not.toContain('機密チーム名')
    expect(warningText).not.toContain('secret-team-id')
    expect(warningText).not.toContain(sessionId)
    expect(
      warning.mock.calls.every((call) =>
        call.every((arg) => typeof arg === 'string'),
      ),
    ).toBe(true)
  })

  it('removeItem が例外を投げても無効値の除去と3操作は止まらない', () => {
    localStorage.setItem(AUTH_STORAGE_KEY, '{not json')
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('remove failed')
    })
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
    expect(store.hasHydrated).toBe(true)
    expect(() => store.signIn({ teamName: 'チーム A' })).not.toThrow()
    expect(() => store.signOut()).not.toThrow()
    expect(() => store.expireSession()).not.toThrow()
    expect(warning).toHaveBeenCalled()
  })

  it('setItem と removeItem がともに失敗してもメモリの認証状態を進める', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('write failed')
    })
    const remove = vi
      .spyOn(Storage.prototype, 'removeItem')
      .mockImplementation(() => {
        throw new Error('remove failed')
      })
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = useAuthStore()

    expect(() => store.signIn({ teamName: 'チーム A' })).not.toThrow()
    expect(store.isAuthenticated).toBe(true)
    expect(remove).toHaveBeenCalledWith(AUTH_STORAGE_KEY)
    expect(() => store.signOut()).not.toThrow()
    expect(store.isAuthenticated).toBe(false)
    expect(() => store.expireSession()).not.toThrow()
    expect(store.sessionExpired).toBe(true)
    expect(warning).toHaveBeenCalled()
  })

  it('保存する JSON に token の語を含めない', () => {
    const store = useAuthStore()
    store.signIn({ teamName: 'チーム A', teamId: 'team-a' })

    expect(localStorage.getItem(AUTH_STORAGE_KEY)).not.toContain('token')
  })
})

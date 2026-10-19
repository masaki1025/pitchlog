import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_INTENT_KEY,
  withAuthIntent,
  writeAuthIntent,
} from '../api/authIntent'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { queryClient } from '../lib/queryClient'
import { AUTH_STORAGE_KEY, useAuthStore } from './authStore'

const a = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const b = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
let pinia: Pinia
beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    locks: {
      request: vi.fn(async (_n, _o, action) => action({ name: 'unit' })),
    },
  })
})
afterEach(() => {
  disposePinia(pinia)
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function authenticated() {
  const auth = useAuthStore()
  setVerifiedAuthForTest(auth, { teamName: '正規A', teamId: a })
  queryClient.setQueryData(['private'], 'A data')
  return auth
}
function empty(auth = useAuthStore()) {
  expect(auth.isAuthenticated).toBe(false)
  expect(auth.teamId).toBeNull()
  expect(auth.teamName).toBeNull()
  expect(queryClient.getQueryCache().getAll()).toEqual([])
}
function event(
  key: string | null = AUTH_INTENT_KEY,
  storageArea: Storage | null = null,
) {
  window.dispatchEvent(
    new StorageEvent('storage', {
      key,
      storageArea,
      newValue: key === null ? null : localStorage.getItem(key),
    }),
  )
}

describe('相関されたsessionだけを保持するauthStore', () => {
  it('初期状態は未検証で同期hydrationを完了', () => {
    const auth = useAuthStore()
    expect(auth.hasHydrated).toBe(true)
    expect(auth.authEpoch).toBe(0)
    expect(auth.canReverify).toBe(false)
    expect(auth.environmentReason).toBeNull()
    empty(auth)
  })
  it.each([
    '{',
    'null',
    '[]',
    '{}',
    JSON.stringify({ version: 1, sessionId: a, teamName: '旧名', teamId: a }),
    JSON.stringify({ teamName: '旧形式' }),
    'x'.repeat(8192),
  ])('旧保存値%sは復元せず消去', (raw) => {
    localStorage.setItem(AUTH_STORAGE_KEY, raw)
    empty()
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
  })
  it('旧signInによる未検証の認証済み化を公開しない', () => {
    expect('signIn' in useAuthStore()).toBe(false)
    empty()
  })
  it('lock外の直接採用を拒否', () => {
    const auth = useAuthStore()
    expect(() => auth.adoptCorrelatedSession(a, a, '入力名', null)).toThrow(
      'lock外',
    )
    empty(auth)
  })
  it('lock内でもpendingや異tenantの採用を拒否', async () => {
    const auth = useAuthStore()
    await withAuthIntent(() => {
      const pending = writeAuthIntent('pending', null)
      auth.beginCorrelatedVerification(pending.intentId)
      expect(() =>
        auth.adoptCorrelatedSession(pending.intentId, a, 'A', null),
      ).toThrow()
      const expected = writeAuthIntent('expected', a)
      auth.beginCorrelatedVerification(expected.intentId)
      expect(() =>
        auth.adoptCorrelatedSession(expected.intentId, b, 'B', null),
      ).toThrow()
    })
    empty(auth)
  })
  it('サーバー確認済みの採用fixtureだけが表示名とIDを設定し、表示名を保存しない', () => {
    const auth = authenticated()
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.teamId).toBe(a)
    expect(auth.teamName).toBe('正規A')
    expect(localStorage.getItem(AUTH_STORAGE_KEY)).toBeNull()
    expect(localStorage.getItem(AUTH_INTENT_KEY)).not.toContain('正規A')
    expect(
      Object.keys(JSON.parse(localStorage.getItem(AUTH_INTENT_KEY)!)),
    ).toEqual(['version', 'intentId', 'phase', 'tenantId'])
  })
  it.each(['beginSessionVerification', 'signOut', 'expireSession'] as const)(
    '%sは記憶とcacheを捨て、認証済み状態を作らない',
    (operation) => {
      const auth = authenticated(),
        epoch = auth.authEpoch,
        marker = localStorage.getItem(AUTH_INTENT_KEY)
      auth[operation]()
      empty(auth)
      expect(auth.authEpoch).toBe(epoch + 1)
      expect(auth.sessionExpired).toBe(operation === 'expireSession')
      expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
    },
  )
  it('同じ意図のsession確認だけでは別タブ用の保存値を変更しない', () => {
    const auth = authenticated(),
      marker = localStorage.getItem(AUTH_INTENT_KEY)!
    auth.beginCorrelatedVerification(JSON.parse(marker).intentId)
    empty(auth)
    expect(localStorage.getItem(AUTH_INTENT_KEY)).toBe(marker)
  })
  it.each([a, b])('別タブの新意図%sは自動採用せず旧cacheを破棄', async (id) => {
    const auth = authenticated(),
      epoch = auth.authEpoch
    await withAuthIntent(() => writeAuthIntent('expected', id))
    event()
    empty(auth)
    expect(auth.authEpoch).toBe(epoch + 1)
    expect(auth.automaticVerificationBlocked).toBe(true)
    expect(auth.explicitLoginRequired).toBe(id !== a)
    expect(auth.canReverify).toBe(id === a)
  })
  it('同じ意図のstorage通知は二重破棄しない', () => {
    const auth = authenticated(),
      epoch = auth.authEpoch
    const clear = vi.spyOn(queryClient, 'clear')
    event()
    event()
    expect(clear).not.toHaveBeenCalled()
    expect(auth.authEpoch).toBe(epoch)
    expect(auth.isAuthenticated).toBe(true)
  })
  it('意図削除・clear通知は未確認にし、保存値から復元しない', () => {
    const auth = authenticated()
    localStorage.removeItem(AUTH_INTENT_KEY)
    event(null)
    empty(auth)
    expect(auth.explicitLoginRequired).toBe(true)
  })
  it.each(['{', '{}', 'null', '[]'])('意図破損%sは旧cacheを破棄', (raw) => {
    const auth = authenticated()
    localStorage.setItem(AUTH_INTENT_KEY, raw)
    auth.syncFromStorage()
    empty(auth)
  })
  it('旧版タブのbb.auth変更も安全側へ無効化するだけで名前やIDを採らない', () => {
    const auth = authenticated()
    localStorage.setItem(
      AUTH_STORAGE_KEY,
      JSON.stringify({ teamName: '別B', teamId: b }),
    )
    event(AUTH_STORAGE_KEY)
    empty(auth)
    expect(auth.explicitLoginRequired).toBe(true)
    const epoch = auth.authEpoch
    event(AUTH_STORAGE_KEY)
    expect(auth.authEpoch).toBe(epoch)
  })
  it('無関係keyやsessionStorageの通知では失効させない', () => {
    const auth = authenticated(),
      epoch = auth.authEpoch
    event('bb.unrelated')
    event(AUTH_INTENT_KEY, sessionStorage)
    expect(auth.authEpoch).toBe(epoch)
    expect(auth.teamId).toBe(a)
  })
  it('保存領域の読取拒否は値や例外を採らず未確認にする', () => {
    const auth = authenticated()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('private-value')
    })
    auth.syncFromStorage()
    empty(auth)
    expect(auth.environmentReason).toBe('storage-unavailable')
    expect(auth.canReverify).toBe(false)
  })
  it('lock機能が失われたら既存の認証済み状態も失効', () => {
    const auth = authenticated()
    vi.stubGlobal('navigator', {})
    auth.syncFromStorage()
    empty(auth)
    expect(auth.environmentReason).toBe('lock-unavailable')
  })
  it('provider再生成は保存expectedがあっても未検証', () => {
    authenticated()
    const p = createPinia()
    setActivePinia(p)
    const next = useAuthStore()
    empty(next)
    expect(next.canReverify).toBe(true)
    disposePinia(p)
  })
})

describe('Cookie不確実通知は拒否専用', () => {
  const noticeKey = 'bb.auth.uncertain'
  const ackKey = 'bb.auth.uncertain.ack'
  it('lock競合中でも通知を保存し、他タブと自分を未確認にする', async () => {
    const auth = authenticated()
    vi.stubGlobal('navigator', {
      locks: { request: vi.fn(async (_n, _o, action) => action(null)) },
    })
    const clear = vi.spyOn(queryClient, 'clear')
    await auth.invalidateUncertainCookie()
    expect(clear).toHaveBeenCalledTimes(1)
    const notice = localStorage.getItem(noticeKey)
    expect(notice).toMatch(/^[0-9a-f-]{36}$/)
    expect(localStorage.getItem(ackKey)).toBeNull()
    empty(auth)
    expect(auth.environmentReason).toBe('lock-busy')
    expect(auth.automaticVerificationBlocked).toBe(true)
  })
  it('通知とackの順序が逆でもstorageだけでは認証済みにならない', () => {
    const auth = authenticated()
    localStorage.setItem(ackKey, b)
    event(ackKey)
    empty(auth)
    localStorage.setItem(noticeKey, b)
    event(noticeKey)
    empty(auth)
    expect(auth.automaticVerificationBlocked).toBe(true)
  })
  it('既読通知とackを両方削除しても認証を復元せず旧採用を拒否', async () => {
    const auth = authenticated()
    await auth.invalidateUncertainCookie()
    const notice = localStorage.getItem(noticeKey)!
    await withAuthIntent(() => {
      const marker = writeAuthIntent('expected', a)
      auth.beginCorrelatedVerification(marker.intentId)
      auth.adoptCorrelatedSession(marker.intentId, a, '正規A', notice)
    })
    expect(auth.isAuthenticated).toBe(true)
    localStorage.removeItem(noticeKey)
    localStorage.removeItem(ackKey)
    auth.syncFromStorage()
    empty(auth)
    expect(auth.automaticVerificationBlocked).toBe(true)
  })
  it.each([noticeKey, ackKey])(
    '%sの不正値で送信前に失効し、同じ通知は二重破棄しない',
    (key) => {
      const auth = authenticated()
      localStorage.setItem(key, 'malformed')
      auth.syncFromStorage()
      empty(auth)
      const epoch = auth.authEpoch
      event(key)
      auth.syncFromStorage()
      expect(auth.authEpoch).toBe(epoch)
      expect(auth.automaticVerificationBlocked).toBe(true)
    },
  )
  it('ackの一致と古い通知の再配信だけでは認証を昇格させない', () => {
    const auth = authenticated()
    localStorage.setItem(noticeKey, a)
    event(noticeKey)
    const epoch = auth.authEpoch
    localStorage.setItem(ackKey, a)
    event(ackKey)
    event(noticeKey)
    empty(auth)
    expect(auth.authEpoch).toBe(epoch)
  })
})

it('通知キーだけ保存不可でも意図無効化を独立に試みる', async () => {
  const auth = authenticated()
  const otherPinia = createPinia()
  try {
    const other = useAuthStore(otherPinia)
    setVerifiedAuthForTest(other, { teamName: '同じAの別タブ', teamId: a })
    expect(other.isAuthenticated).toBe(true)
    const native = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (
      this: Storage,
      key,
      value,
    ) {
      if (key === 'bb.auth.uncertain')
        throw new DOMException('quota', 'QuotaExceededError')
      return native.call(this, key, value)
    })
    await auth.invalidateUncertainCookie()
    expect(JSON.parse(localStorage.getItem(AUTH_INTENT_KEY)!).phase).toBe(
      'verification-required',
    )
    expect(auth.environmentReason).toBe('storage-unavailable')
    empty(auth)
    other.syncFromStorage()
    expect(other.isAuthenticated).toBe(false)
    expect(other.automaticVerificationBlocked).toBe(true)
  } finally {
    disposePinia(otherPinia)
  }
})

it('通知設定と両キー削除が配送前に終わってもイベントから拒否し、再配送は重複破棄しない', () => {
  const auth = authenticated()
  const change = new StorageEvent('storage', {
    key: 'bb.auth.uncertain',
    newValue: b,
  })
  localStorage.setItem('bb.auth.uncertain', b)
  localStorage.removeItem('bb.auth.uncertain')
  window.dispatchEvent(change)
  empty(auth)
  const epoch = auth.authEpoch
  window.dispatchEvent(change)
  expect(auth.authEpoch).toBe(epoch)
  expect(auth.automaticVerificationBlocked).toBe(true)
})

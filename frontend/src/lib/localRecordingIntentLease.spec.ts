import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  AUTH_INTENT_KEY,
  AUTH_INTENT_LOCK,
  AUTH_UNCERTAIN_KEY,
  withAuthIntent,
  writeAuthIntent,
} from '../api/authIntent'
import {
  localIntentMatches,
  withLocalRecordingIntentLease,
  LocalRecordingIntentChanged,
} from './localRecordingIntentLease'

const expected = {
  intentId: '11111111-1111-4111-8111-111111111111',
  tenantId: '22222222-2222-4222-8222-222222222222',
  uncertaintyNotice: null,
}
function mark(phase = 'expected', intentId = expected.intentId) {
  localStorage.setItem(
    AUTH_INTENT_KEY,
    JSON.stringify({
      version: 1,
      intentId,
      phase,
      tenantId: expected.tenantId,
    }),
  )
}
function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}
beforeEach(() => {
  localStorage.clear()
  mark()
  const held = new Set<string>()
  vi.stubGlobal('navigator', {
    locks: {
      request: async (
        name: string,
        _options: unknown,
        callback: (lock: unknown) => unknown,
      ) => {
        if (held.has(name)) return callback(null)
        held.add(name)
        try {
          return await callback({ name, mode: 'exclusive' })
        } finally {
          held.delete(name)
        }
      },
    },
  })
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('local IDB待機中も同名leaseを保持し、認証採用資格を作らない', async () => {
  const wait = deferred(),
    entered = deferred()
  const first = withLocalRecordingIntentLease(expected, async () => {
    entered.release()
    expect(() => writeAuthIntent('expected', expected.tenantId)).toThrow(
      '認証意図lock外',
    )
    await wait.promise
    return 'local-only'
  })
  await entered.promise
  const mutation = vi.fn()
  await expect(withAuthIntent(mutation)).rejects.toMatchObject({
    reason: 'lock-busy',
  })
  expect(mutation).not.toHaveBeenCalled()
  await expect(
    withLocalRecordingIntentLease(expected, async () => 'other'),
  ).rejects.toMatchObject({ reason: 'lock-busy' })
  wait.release()
  await expect(first).resolves.toBe('local-only')
  expect(localIntentMatches(expected)).toBe(true)
})
it.each(['pending', 'verification-required', 'signed-out'])(
  '%sの意図を端末内入力の資格へ変換しない',
  async (phase) => {
    mark(phase)
    const operation = vi.fn()
    await expect(
      withLocalRecordingIntentLease(expected, operation),
    ).rejects.toBeInstanceOf(LocalRecordingIntentChanged)
    expect(operation).not.toHaveBeenCalled()
  },
)
it('新nonceへ相関条件を持ち越さない', async () => {
  mark('expected', '33333333-3333-4333-8333-333333333333')
  expect(localIntentMatches(expected)).toBe(false)
})
it('規約外のstorage変更も前後検査で拒否し、既保存値を成功と返さない', async () => {
  const retained: string[] = []
  await expect(
    withLocalRecordingIntentLease(expected, async () => {
      retained.push('original pending body')
      mark('signed-out')
      return 'do-not-return-success'
    }),
  ).rejects.toBeInstanceOf(LocalRecordingIntentChanged)
  expect(retained).toEqual(['original pending body'])
})
it('新しい不確実通知を確認済みへ更新しない', async () => {
  await expect(
    withLocalRecordingIntentLease(expected, async () => {
      localStorage.setItem(
        AUTH_UNCERTAIN_KEY,
        '33333333-3333-4333-8333-333333333333',
      )
    }),
  ).rejects.toBeInstanceOf(LocalRecordingIntentChanged)
})
it('失敗したlocal操作後にもleaseを解放する', async () => {
  await expect(
    withLocalRecordingIntentLease(expected, async () => {
      throw new Error('storage failed')
    }),
  ).rejects.toThrow('storage failed')
  await expect(
    withLocalRecordingIntentLease(expected, async () => 7),
  ).resolves.toBe(7)
})
it('Web Locksなしでcallbackを実行しない', async () => {
  vi.stubGlobal('navigator', {})
  const operation = vi.fn()
  await expect(
    withLocalRecordingIntentLease(expected, operation),
  ).rejects.toMatchObject({ reason: 'lock-unavailable' })
  expect(operation).not.toHaveBeenCalled()
  expect(AUTH_INTENT_LOCK).toBe('pitchlog.auth.intent')
})

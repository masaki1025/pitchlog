import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  AUTH_INTENT_KEY,
  AUTH_INTENT_LOCK,
  AuthEnvironmentError,
  readAuthIntent,
  withAuthIntent,
  writeAuthIntent,
} from './authIntent'

const id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const valid = { version: 1, intentId: id, phase: 'expected', tenantId: id }
beforeEach(() => {
  localStorage.clear()
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
describe('認証意図の厳密構造・排他契約', () => {
  it.each([
    null,
    [],
    {},
    { ...valid, version: 2 },
    { ...valid, intentId: 'bad' },
    { ...valid, phase: ['expected'] },
    { ...valid, phase: 'other' },
    { ...valid, tenantId: null },
    { ...valid, tenantId: 'bad' },
    { ...valid, tenantId: id.toUpperCase() },
    { ...valid, password: 'not-allowed' },
    { ...valid, phase: 'pending' },
    { ...valid, phase: 'signed-out' },
    { ...valid, phase: 'verification-required', tenantId: 1 },
  ])('不正意図%jを復元しない', (value) => {
    localStorage.setItem(AUTH_INTENT_KEY, JSON.stringify(value))
    expect(readAuthIntent()).toBeNull()
  })
  it.each([
    valid,
    { ...valid, phase: 'verification-required' },
    { ...valid, phase: 'verification-required', tenantId: null },
    { ...valid, phase: 'pending', tenantId: null },
    { ...valid, phase: 'signed-out', tenantId: null },
  ])('相関制約%jの構造だけを読む', (value) => {
    localStorage.setItem(AUTH_INTENT_KEY, JSON.stringify(value))
    expect(readAuthIntent()).toEqual(value)
  })
  it.each(['{', 'x'.repeat(1025)])('破損・過大値を採らない', (value) => {
    localStorage.setItem(AUTH_INTENT_KEY, value)
    expect(readAuthIntent()).toBeNull()
  })
  it('exclusive/ifAvailableだけを使い、更新・再読・採用を同じcallback内で行う', async () => {
    let held = false
    const request = vi.fn(async (_name, _options, callback) => {
      held = true
      const result = callback({ name: AUTH_INTENT_LOCK })
      expect(result).not.toBeInstanceOf(Promise)
      held = false
      return result
    })
    vi.stubGlobal('navigator', { locks: { request } })
    const adopted = await withAuthIntent(() => {
      expect(held).toBe(true)
      const next = writeAuthIntent('expected', id)
      expect(readAuthIntent()).toEqual(next)
      return next
    })
    expect(request).toHaveBeenCalledWith(
      AUTH_INTENT_LOCK,
      { mode: 'exclusive', ifAvailable: true },
      expect.any(Function),
    )
    expect(readAuthIntent()).toEqual(adopted)
  })
  it('lock busy時はcallbackを実行せず待機・再試行しない', async () => {
    const action = vi.fn()
    const request = vi.fn(async (_name, _options, callback) => callback(null))
    vi.stubGlobal('navigator', { locks: { request } })
    await expect(withAuthIntent(action)).rejects.toMatchObject({
      reason: 'lock-busy',
    })
    expect(action).not.toHaveBeenCalled()
    expect(request).toHaveBeenCalledTimes(1)
  })
  it('storage読取拒否の理由を公開し、保存値・例外本文を公開しない', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('private')
    })
    expect(() => readAuthIntent()).toThrow(AuthEnvironmentError)
    expect(() => readAuthIntent()).toThrow('storage-unavailable')
  })
  it('storage書込が反映されない場合も採用しない', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => undefined)
    expect(() => writeAuthIntent('pending', null)).toThrow(
      'storage-unavailable',
    )
  })
})

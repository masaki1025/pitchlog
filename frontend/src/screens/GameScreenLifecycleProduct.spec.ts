// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://pitchlog.test"}
/** 製品mountの実環境供給を検査する。HTTP/DBの代替証拠ではない。 */
import 'fake-indexeddb/auto'
import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia, disposePinia, type Pinia } from 'pinia'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import * as lifecycle from './gameLifecycleController'
import GameScreenLifecycleProduct from './GameScreenLifecycleProduct.vue'

const createWriter = lifecycle.createGameLifecycleWriter
let pinia: Pinia
let writer: ReturnType<typeof createWriter>
beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: '11111111-1111-4111-8111-111111111111',
    teamName: '記録チーム',
  })
  vi.spyOn(lifecycle, 'createGameLifecycleWriter').mockImplementation(
    (environment) => {
      writer = createWriter(environment)
      return writer
    },
  )
  vi.spyOn(
    lifecycle.GameLifecycleController.prototype,
    'refresh',
  ).mockImplementation(async function (
    this: lifecycle.GameLifecycleController,
  ) {
    return this.view
  })
})
afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('環境確認と実HTTPS状態をwriterへ毎回供給し、常時trueにしない', async () => {
  const wrapper = mount(GameScreenLifecycleProduct, {
    props: { gameId: '22222222-2222-4222-8222-222222222222' },
  })
  await flushPromises()
  expect(await writer.resolvePreconditions!()).toEqual({
    topLevelHttps: true,
    sameBrowserProfile: false,
    sameBrowsingMode: false,
    sameStorageBucket: false,
    siteStorageAvailable: true,
    lockdownModeNotApplied: false,
  })
  for (const box of wrapper.findAll('input[type=checkbox]'))
    await box.setValue(true)
  expect(await writer.resolvePreconditions!()).toEqual({
    topLevelHttps: true,
    sameBrowserProfile: true,
    sameBrowsingMode: true,
    sameStorageBucket: true,
    siteStorageAvailable: true,
    lockdownModeNotApplied: true,
  })
  vi.stubGlobal('isSecureContext', false)
  expect((await writer.resolvePreconditions!())?.topLevelHttps).toBe(false)
  wrapper.unmount()
})

it('認証epoch変更時に古いcontrollerを失効させる', async () => {
  const disposed = vi.spyOn(
    lifecycle.GameLifecycleController.prototype,
    'dispose',
  )
  const wrapper = mount(GameScreenLifecycleProduct, {
    props: { gameId: '22222222-2222-4222-8222-222222222222' },
  })
  await flushPromises()
  useAuthStore().expireSession()
  await flushPromises()
  expect(disposed).toHaveBeenCalledOnce()
  expect(wrapper.emitted('resume-recording')).toBeUndefined()
  wrapper.unmount()
})

import { ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { pinia, installAppProviders } from './appProviders'
import { useAuthStore } from './stores/authStore'
import * as local from './lib/localRecordingSession'
import * as authApi from './api/auth'
import { createAppRouter } from './router'
import App from './App.vue'
const game = '59c28087-e5d8-43e1-9e50-65833ad0cae6'
// App/実routerの表示境界だけの対向。資格真正性は実IDB試験・owned画面で別検証。
function scope() {
  const current = ref(true)
  const object = {
    gameId: game,
    get current() {
      return current.value
    },
    context: {},
    identity: () => ({ tenantId: game, epoch: 1, verified: false }),
    dispose: vi.fn(() => {
      current.value = false
    }),
  }
  vi.spyOn(local, 'isLocalRecordingSession').mockImplementation(
    (value): value is local.LocalRecordingSession => value === object,
  )
  return object as unknown as local.LocalRecordingSession
}
beforeEach(() => {
  localStorage.clear()
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  auth.signOut()
  auth.hasHydrated = true
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
async function opened() {
  const saved = scope()
  vi.spyOn(local.LocalRecordingSession, 'restore').mockResolvedValue(saved)
  vi.spyOn(local, 'recordingBackendReachability').mockResolvedValue(
    'unavailable',
  )
  const router = createAppRouter(createMemoryHistory())
  await router.push(`/games/${game}/record?recording=play-prefix-v3`)
  const wrapper = mount(App, {
    global: {
      plugins: [{ install: installAppProviders }, router],
      stubs: { GameScreenOrdinaryPitch: true, GameScreenEntryRecordHost: true },
    },
  })
  await flushPromises()
  return { router, wrapper, saved }
}
it('未認証を認証済みにせず、guard受理済みの端末内記録だけをAppが表示する', async () => {
  const { router, wrapper } = await opened()
  expect(wrapper.get('h1').text()).toBe('端末内の記録')
  expect(useAuthStore(pinia).isAuthenticated).toBe(false)
  expect(wrapper.find('nav[aria-label="画面移動"]').exists()).toBe(false)
  vi.spyOn(authApi, 'ensureSessionVerified').mockRejectedValue(new Error('401'))
  await router.push('/team')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('login')
  expect(wrapper.text()).not.toContain('端末内の記録')
  wrapper.unmount()
})
it('保存scope失効はApp表示を失効し、サーバー認証を補完しない', async () => {
  const { router, wrapper, saved } = await opened()
  saved.dispose()
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('login')
  expect(useAuthStore(pinia).isAuthenticated).toBe(false)
  wrapper.unmount()
})
it('同じ端末内記録からの再接続中は保護内容を隠し、guardの実認証結果を待つ', async () => {
  const { router, wrapper } = await opened()
  vi.mocked(local.LocalRecordingSession.restore).mockResolvedValue(null)
  let reject!: (reason: Error) => void
  const verify = vi.spyOn(authApi, 'ensureSessionVerified').mockReturnValue(
    new Promise((_r, failure) => {
      reject = failure
    }),
  )
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(verify).toHaveBeenCalledOnce()
  expect(router.currentRoute.value.name).toBe('game-record')
  expect(wrapper.text()).toContain('接続と保存済みの記録を確認しています')
  expect(wrapper.find('game-screen-ordinary-pitch-stub').exists()).toBe(false)
  reject(new Error('401'))
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('login')
  wrapper.unmount()
})

it('端末内記録から公開ガイドへ移動しても中間状態でloginへ割り込まない', async () => {
  const { router, wrapper } = await opened()
  const verify = vi.spyOn(authApi, 'ensureSessionVerified')
  await router.push('/help')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('help')
  expect(verify).not.toHaveBeenCalled()
  wrapper.unmount()
})

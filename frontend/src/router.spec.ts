import { flushPromises, mount } from '@vue/test-utils'
import type { Plugin } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import { installAppProviders, pinia } from './appProviders'
import { createAppRouter } from './router'
import { useAuthStore } from './stores/authStore'

const sharedProviders: Plugin = {
  install(app) {
    installAppProviders(app)
  },
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('公開ガイド経路', () => {
  it('未ログインでも /help へ直接到達できる', async () => {
    useAuthStore(pinia).signOut()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/help')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [sharedProviders, router] },
    })

    expect(useAuthStore(pinia).isAuthenticated).toBe(false)
    expect(wrapper.get('h1').text()).toBe('使い方')
    expect(wrapper.text()).toContain('チーム・選手を準備')
    expect(router.currentRoute.value.name).toBe('help')
    wrapper.unmount()
  })

  it('トップとガイドを往復してもテナントデータを取得しない', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()
    const wrapper = mount(App, {
      global: { plugins: [sharedProviders, router] },
    })
    const authStore = useAuthStore(pinia)

    await wrapper.get('a[aria-label="使い方を開く"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('help')
    expect(wrapper.get('h1').text()).toBe('使い方')

    await wrapper.get('button[aria-label="戻る"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('home')
    expect(wrapper.get('h1').text()).toBe('PitchLog')
    expect(useAuthStore(pinia)).toBe(authStore)
    expect(fetchSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

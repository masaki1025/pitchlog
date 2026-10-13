import { mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'
import App from './App.vue'
import { createAppRouter } from './router'

describe('公開ガイド経路', () => {
  it('/help へ直接到達するとガイドを描画する', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/help')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.get('h1').text()).toBe('使い方')
    expect(wrapper.text()).toContain('チーム・選手を準備')
    expect(router.currentRoute.value.name).toBe('help')
    wrapper.unmount()
  })
})

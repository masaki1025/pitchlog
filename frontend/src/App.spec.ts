import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from './App.vue'

describe('App', () => {
  it('PitchLog を描画する', () => {
    const wrapper = mount(App)

    expect(wrapper.text()).toContain('PitchLog')
  })
})

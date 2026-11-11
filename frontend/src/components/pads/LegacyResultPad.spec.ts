import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LegacyResultPad from './LegacyResultPad.vue'

function mountPad(overrides: Record<string, unknown> = {}) {
  return mount(LegacyResultPad, {
    props: {
      balls: 0,
      strikes: 0,
      outs: 0,
      hitAvailable: true,
      hasRunners: false,
      hasFirst: false,
      hasThird: false,
      ...overrides,
    },
  })
}

describe('LegacyResultPad', () => {
  it('走者なし0死でも犠打を選べる', () => {
    const wrapper = mountPad()
    expect(
      wrapper
        .get('[data-result-id="batting-result.sacrifice-bunt"]')
        .attributes('disabled'),
    ).toBeUndefined()
  })

  it('2死では犠打を選べない', () => {
    const wrapper = mountPad({ outs: 2 })
    expect(
      wrapper
        .get('[data-result-id="batting-result.sacrifice-bunt"]')
        .attributes('disabled'),
    ).toBeDefined()
  })

  it('走者なしでは野手選択を選べない', async () => {
    const wrapper = mountPad()
    await wrapper
      .get('[data-result-id="batting-result.single"]')
      .trigger('click')
    expect(wrapper.emitted('select-in-play')).toHaveLength(1)
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '全打球')!
      .trigger('click')
    expect(
      wrapper
        .get('[data-result-id="batting-result.fielders-choice"]')
        .attributes('disabled'),
    ).toBeDefined()
  })

  it('打球入力不可のときは打球結果を選べない', () => {
    const wrapper = mountPad({ hitAvailable: false })
    expect(
      wrapper
        .get('[data-result-id="batting-result.single"]')
        .attributes('disabled'),
    ).toBeDefined()
  })
})

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

  it('2ストライク未満は三振詳細を選べない', () => {
    const wrapper = mountPad({ strikes: 1 })
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text().includes('三振詳細'))!
        .attributes('disabled'),
    ).toBeDefined()
  })

  it('2ストライクは三振詳細を選べる', () => {
    const wrapper = mountPad({ strikes: 2 })
    expect(
      wrapper
        .findAll('button')
        .find((button) => button.text().includes('三振詳細'))!
        .attributes('disabled'),
    ).toBeUndefined()
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

it('PB/WPを付加結果として通知し、付加結果中は打球結果を止める', async () => {
  const wrapper = mountPad()
  const pb = wrapper.findAll('button').find((button) => button.text() === 'PB')
  expect(pb).toBeDefined()
  await pb!.trigger('click')
  expect(wrapper.emitted('secondary')).toEqual([
    ['secondary-result.passed-ball'],
  ])
  const wp = wrapper.findAll('button').find((button) => button.text() === 'WP')
  await wp!.trigger('click')
  expect(wrapper.emitted('secondary')).toHaveLength(2)
  await wrapper.setProps({ secondaryPending: 'PB' })
  expect(
    wrapper
      .get('[data-result-id="batting-result.single"]')
      .attributes('disabled'),
  ).toBeDefined()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '解除')!
    .trigger('click')
  expect(wrapper.emitted('clearSecondary')).toHaveLength(1)
})

it('打撃妨害・守備妨害・ボークを通知する', async () => {
  const wrapper = mountPad()
  for (const label of ['打撃妨害', '守備妨害', 'ボーク']) {
    await wrapper
      .findAll('button')
      .find((button) => button.text() === label)!
      .trigger('click')
  }
  expect(wrapper.emitted('interference')).toEqual([
    ['secondary-result.batting-interference'],
    ['secondary-result.obstruction'],
  ])
  expect(wrapper.emitted('balk')).toEqual([['secondary-result.balk']])
})

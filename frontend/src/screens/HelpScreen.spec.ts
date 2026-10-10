import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HelpScreen from './HelpScreen.vue'

describe('HelpScreen', () => {
  it('5 段の手順カードを順序どおりに描画する', () => {
    const wrapper = mount(HelpScreen)
    const cards = wrapper.get('section.mb-4').findAll('article')

    expect(cards).toHaveLength(5)
    expect(cards.map((card) => card.get('h2').text())).toEqual([
      'チーム・選手を準備',
      '試合を作成',
      '1球ずつ入力',
      '保存・再開',
      '確認・分析',
    ])
  })

  it('戻るボタンを押すと payload なしの back を 1 回 emit する', async () => {
    const wrapper = mount(HelpScreen)

    await wrapper.get('button[aria-label="戻る"]').trigger('click')

    const backEvents = wrapper.emitted().back
    expect(backEvents).toHaveLength(1)
    expect(backEvents?.[0]).toEqual([])
  })

  it('外部依存を注入せずに単体でマウントできる', () => {
    const wrapper = mount(HelpScreen)

    expect(wrapper.exists()).toBe(true)
  })
})

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GameScreen from './GameScreen.vue'

describe('GameScreen の試合状態表示', () => {
  it('呼出元の整形済み文字列を変更せず表示する', () => {
    const wrapper = mount(GameScreen, {
      props: {
        state: {
          gameName: '筑波大 対 東京大',
          inning: '7回',
          half: '表',
          awayScore: '3',
          homeScore: '2',
          outs: '1アウト',
          runners: '一・三塁',
          count: '2ボール 1ストライク',
          batter: '打者 山田',
          pitcher: '投手 佐藤',
        },
      },
    })

    expect(wrapper.get('[data-testid="game-name"]').text()).toBe(
      '筑波大 対 東京大',
    )
    expect(wrapper.get('[data-testid="inning"]').text()).toBe('7回')
    expect(wrapper.get('[data-testid="half"]').text()).toBe('表')
    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('3')
    expect(wrapper.get('[data-testid="home-score"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="outs"]').text()).toBe('1アウト')
    expect(wrapper.get('[data-testid="runners"]').text()).toBe('一・三塁')
    expect(wrapper.get('[data-testid="count"]').text()).toBe(
      '2ボール 1ストライク',
    )
    expect(wrapper.get('[data-testid="batter"]').text()).toBe('打者 山田')
    expect(wrapper.get('[data-testid="pitcher"]').text()).toBe('投手 佐藤')
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('未供給・欠損・空文字の値を未取得と表示する', async () => {
    const wrapper = mount(GameScreen)

    expect(wrapper.findAll('[data-testid]').map((node) => node.text())).toEqual(
      Array(10).fill('未取得'),
    )

    await wrapper.setProps({ state: { gameName: '', awayScore: null } })
    expect(wrapper.get('[data-testid="game-name"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('未取得')
  })

  it('生数値が実行時に混入しても表示せず未取得にする', () => {
    const wrapper = mount(GameScreen, {
      props: {
        state: { awayScore: 3, count: 2 } as unknown as {
          awayScore: string
          count: string
        },
      },
    })

    expect(wrapper.get('[data-testid="away-score"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="count"]').text()).toBe('未取得')
  })

  it('利用者文字列をHTMLとして解釈しない', () => {
    const input = '<img src=x onerror=alert(1)>'
    const wrapper = mount(GameScreen, {
      props: { state: { gameName: input, batter: input } },
    })

    expect(wrapper.get('[data-testid="game-name"]').text()).toBe(input)
    expect(wrapper.get('[data-testid="batter"]').text()).toBe(input)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.html()).toContain('&lt;img')
  })
})

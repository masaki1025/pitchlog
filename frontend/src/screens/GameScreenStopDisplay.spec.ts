import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import type { StopDisplay } from './GameScreenStopDisplay'

afterEach(() => vi.restoreAllMocks())

function expectActionsBlocked(
  wrapper: ReturnType<typeof mount<typeof GameScreen>>,
) {
  for (const testId of ['resume-same-content', 'correct-stopped-content']) {
    const button = wrapper.get<HTMLButtonElement>(`[data-testid="${testId}"]`)
    expect(button.element.disabled).toBe(true)
    expect(button.attributes('type')).toBe('button')
    expect(button.attributes('aria-describedby')).toBe('stop-actions-blocked')
  }
  expect(
    wrapper.get<HTMLButtonElement>('[data-testid="commit-pitch"]').element
      .disabled,
  ).toBe(true)
}

describe('GameScreen の停止表示契約', () => {
  it('未供給は停止・端末未確認件数とも未取得に倒し、送信を封鎖する', () => {
    const wrapper = mount(GameScreen)

    expect(wrapper.get('[data-testid="stop-status"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="device-unconfirmed-count"]').text()).toBe(
      '未取得',
    )
    expect(wrapper.get('[data-testid="correction-status"]').text()).toContain(
      '未取得',
    )
    expect(wrapper.get('[data-testid="stop-hold-note"]').text()).toContain(
      '後続記録',
    )
    expect(wrapper.get('[data-testid="stop-hold-note"]').text()).toContain(
      '自動送信したりしません',
    )
    expect(wrapper.get('[data-testid="stop-actions-blocked"]').text()).toBe(
      '送信の状態を十分に確認できないため、今は送信の再開も内容の訂正もできません。',
    )
    for (const word of ['実接続', '未提供', '保持する扱い']) {
      expect(
        wrapper.get('section[aria-label="送信停止と再開"]').text(),
      ).not.toContain(word)
    }
    expect(wrapper.text()).toContain('終了した試合の再開とは別')
    expectActionsBlocked(wrapper)
  })

  it.each([
    [
      '0件',
      {
        phase: 'sending-stopped',
        deviceUnconfirmed: { kind: 'count', value: 0 },
      },
      '送信停止',
      '0',
    ],
    [
      '件数未取得',
      {
        phase: 'confirmation-pending',
        deviceUnconfirmed: { kind: 'unavailable' },
      },
      '確認待ち（送信停止）',
      '未取得',
    ],
    [
      '件数読取失敗',
      { phase: 'sending-stopped', deviceUnconfirmed: { kind: 'read-failed' } },
      '送信停止',
      '読取失敗',
    ],
    ['状態読取失敗', { phase: 'read-failed' }, '読取失敗', '未取得'],
    [
      '再開照会中',
      {
        phase: 'resume-inquiry',
        deviceUnconfirmed: { kind: 'count', value: 2 },
      },
      '再開照会中（送信停止）',
      '2',
    ],
  ] as const)(
    '%s を独立した受取表示として描画する',
    (_name, stopDisplay, status, count) => {
      const wrapper = mount(GameScreen, { props: { stopDisplay } })

      expect(wrapper.get('[data-testid="stop-status"]').text()).toBe(status)
      expect(
        wrapper.get('[data-testid="device-unconfirmed-count"]').text(),
      ).toBe(count)
      expectActionsBlocked(wrapper)
    },
  )

  it('不正な件数は0に丸めず未取得とする', () => {
    const wrapper = mount(GameScreen, {
      props: {
        stopDisplay: {
          phase: 'sending-stopped',
          deviceUnconfirmed: { kind: 'count', value: -1 },
        },
      },
    })
    expect(wrapper.get('[data-testid="device-unconfirmed-count"]').text()).toBe(
      '未取得',
    )
  })

  it('表示契約外の内部文言や他tenantの存在情報をそのまま出さない', () => {
    const secret = '他tenantの原本が存在する <img src=x>'
    const wrapper = mount(GameScreen, {
      props: {
        stopDisplay: {
          phase: secret as 'unavailable',
          correctionNotice: secret as 'commit-unknown',
        },
      },
    })

    expect(wrapper.get('[data-testid="stop-status"]').text()).toBe('未取得')
    expect(wrapper.get('[data-testid="correction-status"]').text()).toBe(
      '訂正の安全確認が完了していません。',
    )
    expect(wrapper.text()).not.toContain(secret)
    expect(wrapper.find('img').exists()).toBe(false)
    expectActionsBlocked(wrapper)
  })

  it.each([
    ['commit不明', 'commit-unknown'],
    ['旧要求遮断未確認', 'old-request-block-unconfirmed'],
    ['取消証拠なし', 'cancellation-evidence-missing'],
  ] as const)(
    '%s の表示fixtureでも訂正不可で、内部の事情を表示しない',
    (_name, correctionNotice) => {
      const wrapper = mount(GameScreen, {
        props: { stopDisplay: { phase: 'sending-stopped', correctionNotice } },
      })

      expect(wrapper.get('[data-testid="correction-status"]').text()).toBe(
        '訂正の安全確認が完了していません。',
      )
      expect(
        wrapper.get<HTMLButtonElement>(
          '[data-testid="correct-stopped-content"]',
        ).element.disabled,
      ).toBe(true)
      expect(wrapper.text()).not.toContain(correctionNotice)
      expectActionsBlocked(wrapper)
    },
  )

  it('disabled ボタンへのプログラム的 click でも emit・送信・保存しない', () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response())
    const storageSpy = vi.spyOn(Storage.prototype, 'setItem')
    const wrapper = mount(GameScreen, {
      props: {
        stopDisplay: {
          phase: 'sending-stopped',
          deviceUnconfirmed: { kind: 'count', value: 3 },
        },
      },
    })

    for (const testId of ['resume-same-content', 'correct-stopped-content']) {
      wrapper
        .get(`[data-testid="${testId}"]`)
        .element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
    expect(wrapper.emitted()).toEqual({})
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(storageSpy).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('保存しました')
    expectActionsBlocked(wrapper)
  })

  it('再mountの表示fixtureを再描画し、独立した2インスタンスの値を混ぜない', async () => {
    // 受取fixtureの再供給だけを検査する。耐久providerの再読込試験ではない。
    const firstFixture: StopDisplay = {
      phase: 'sending-stopped',
      deviceUnconfirmed: { kind: 'count', value: 4 },
    }
    const first = mount(GameScreen, { props: { stopDisplay: firstFixture } })
    first.unmount()
    const remounted = mount(GameScreen, {
      props: { stopDisplay: firstFixture },
    })
    const other = mount(GameScreen, {
      props: {
        stopDisplay: {
          phase: 'resume-inquiry',
          deviceUnconfirmed: { kind: 'count', value: 1 },
        },
      },
    })

    expect(
      remounted.get('[data-testid="device-unconfirmed-count"]').text(),
    ).toBe('4')
    expect(other.get('[data-testid="device-unconfirmed-count"]').text()).toBe(
      '1',
    )
    await remounted.setProps({
      stopDisplay: {
        phase: 'confirmation-pending',
        deviceUnconfirmed: { kind: 'count', value: 5 },
      },
    })
    expect(remounted.get('[data-testid="stop-status"]').text()).toBe(
      '確認待ち（送信停止）',
    )
    expect(
      remounted.get('[data-testid="device-unconfirmed-count"]').text(),
    ).toBe('5')
    expect(other.get('[data-testid="stop-status"]').text()).toBe(
      '再開照会中（送信停止）',
    )
    expect(other.get('[data-testid="device-unconfirmed-count"]').text()).toBe(
      '1',
    )
    expectActionsBlocked(remounted)
    expectActionsBlocked(other)
  })
})

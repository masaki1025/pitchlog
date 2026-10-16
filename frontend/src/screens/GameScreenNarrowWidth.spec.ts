import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { actionRequiredLabelId, queueStateId } from '../lib/sync/queueState'
import GameScreen from './GameScreen.vue'
import { PITCH_COMMIT_BLOCK_REASON } from './GameScreenCommitGate'

/**
 * NFR-020 の 375px 幅。
 *
 * jsdom はレイアウトを計算しないので、描画後の実ピクセルは測れない。ここで固定
 * するのは【横溢れを生む構造条件を持たないこと】と【狭い幅で読めている必要が
 * ある表示が出ていること】の 2 つで、実寸の確認は E2E に残る。
 */
const NARROW_WIDTH = 375

function mountNarrow() {
  window.innerWidth = NARROW_WIDTH
  window.dispatchEvent(new Event('resize'))
  return mount(GameScreen, {
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
      queueSlots: [
        { state: queueStateId('未送信') },
        {
          state: queueStateId('要操作'),
          actionRequiredLabel: actionRequiredLabelId('管理者対応待ち'),
        },
      ],
      storagePersistence: 'denied',
    },
  })
}

describe('375px 幅で横溢れを生む構造を持たない', () => {
  it('375px より広い固定幅・最小幅を宣言しない', () => {
    const html = mountNarrow().html()

    // Tailwind の任意値指定（w-[400px] など）と、固定の最小幅を拾う。
    const widths = [...html.matchAll(/\b(?:min-)?w-\[(\d+)px\]/g)].map(
      (match) => Number(match[1]),
    )
    for (const width of widths) {
      expect(width).toBeLessThanOrEqual(NARROW_WIDTH)
    }

    // 既定スケールの最大幅は親に収まる指定だけを使う（max-w-* は縮む側）。
    expect(html).not.toMatch(/\bmin-w-(?:sm|md|lg|xl|\d{2,})\b/)
  })

  it('入力欄を並べる横並びが縮める指定を持つ', () => {
    const wrapper = mountNarrow()

    // min-w-0 が無い flex の子は、内容幅で押し広げて横スクロールを生む。
    for (const testId of ['pitch-type', 'pitch-speed', 'pitch-result']) {
      expect(wrapper.get(`[data-testid="${testId}"]`).classes()).toContain(
        'min-w-0',
      )
    }
  })

  it('2 列の並びを狭い幅では 1 列にする', () => {
    const html = mountNarrow().html()

    // sm: の接頭辞が無い grid-cols-N（N >= 3）は 375px で詰まる。
    expect(html).not.toMatch(/(?<!:)\bgrid-cols-(?:[3-9]|1[0-2])\b/)
  })
})

describe('375px 幅で読めている必要がある表示', () => {
  it('未送信件数・要操作・確定できない理由がすべて出ている', () => {
    const wrapper = mountNarrow()

    expect(wrapper.get('[data-testid="unsent-count"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="action-required-count"]').text()).toBe(
      '1',
    )
    expect(wrapper.get('[data-testid="action-required-labels"]').text()).toBe(
      '管理者対応待ち',
    )
    expect(wrapper.get('[data-testid="commit-blocked-reason"]').text()).toBe(
      PITCH_COMMIT_BLOCK_REASON,
    )
    expect(wrapper.get('[data-testid="sync-notices"]').text()).toContain(
      '永続ストレージの要求が拒否された',
    )
  })

  it('長い文面を折り返さない指定にしていない', () => {
    const wrapper = mountNarrow()

    for (const testId of ['commit-blocked-reason', 'sync-notices']) {
      expect(wrapper.get(`[data-testid="${testId}"]`).classes()).not.toContain(
        'whitespace-nowrap',
      )
    }
  })
})

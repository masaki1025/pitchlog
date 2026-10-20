import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { actionRequiredLabelId } from '../lib/sync/queueState'
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

function mountNarrow(width = NARROW_WIDTH) {
  window.innerWidth = width
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
      courseView: { plateSide: '右', viewpoint: 'pitcher' as const },
      pitchTypes: [{ id: 'fastball', displayName: '直球', enabled: true }],
      results: [{ id: 'ball', displayName: 'ボール', enabled: true }],
      unsentCount: 1,
      actionRequired: {
        count: 1,
        labels: [actionRequiredLabelId('管理者対応待ち')],
      },
      evacuatedCount: 0,
      storagePersistence: 'denied',
      stopDisplay: {
        phase: 'confirmation-pending',
        deviceUnconfirmed: { kind: 'count', value: 12 },
      },
    },
  })
}

describe('375px 幅で横溢れを生む構造を持たない', () => {
  it('375px より広い固定幅・最小幅を宣言しない', () => {
    const html = mountNarrow().html()

    // Tailwind の任意値指定（w-[400px] など）。
    const arbitrary = [...html.matchAll(/\b(?:min-)?w-\[(\d+)px\]/g)].map(
      (match) => Number(match[1]),
    )
    // 既定スケール（w-96 = 24rem = 384px）。1 単位 = 4px で換算する。
    // max-w-* は縮む側なので対象外(w-80 に一致してしまうのを避ける)。
    const scaled = [...html.matchAll(/(^|[\s"])(?:min-)?w-(\d+)\b/g)].map(
      (match) => Number(match[2]) * 4,
    )

    for (const width of [...arbitrary, ...scaled]) {
      expect(width).toBeLessThanOrEqual(NARROW_WIDTH)
    }

    // 名前付きの最小幅と、inline の固定幅も使わない。
    expect(html).not.toMatch(/\bmin-w-(?:sm|md|lg|xl|\d{2,})\b/)
    expect(html).not.toMatch(/style="[^"]*width:/)
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
    const wrapper = mountNarrow()
    const html = wrapper.html()

    // 暗黙のauto列は、日本語フォントの入力/消去ボタンの最小内容幅で広がる。
    // 明示した1fr列の最小幅0を使い、375pxの内容幅に収める。
    expect(
      wrapper.get('[aria-label="投球入力の下書き"] .grid').classes(),
    ).toContain('grid-cols-1')

    // sm: の接頭辞が無い grid-cols-N（N >= 3）は 375px で詰まる。
    expect(html).not.toMatch(/(?<!:)\bgrid-cols-(?:[3-9]|1[0-2])\b/)
  })
})

describe('375px 幅で読めている必要がある表示', () => {
  it('長い英数字の試合名・選手名を省略せず、単語内でも折り返せる', () => {
    const name = 'W'.repeat(120)
    const wrapper = mount(GameScreen, {
      props: { state: { gameName: name, batter: name, pitcher: name } },
    })

    for (const testId of ['game-name', 'batter', 'pitcher']) {
      expect(wrapper.get(`[data-testid="${testId}"]`).text()).toBe(name)
    }
    // jsdomは実幅を計算しない。実ブラウザで横溢れを再現した入力を保持し、
    // 単語内の折り返しを各表示へ継承する。実寸は別途Chromiumで測る。
    expect(wrapper.get('main').classes()).toContain('wrap-anywhere')
  })

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
      const classes = wrapper.get(`[data-testid="${testId}"]`).classes()
      for (const forbidden of [
        'whitespace-nowrap',
        'whitespace-pre',
        'truncate',
      ]) {
        expect(classes).not.toContain(forbidden)
      }
    }
  })

  it.each([375, 320])(
    '%dpx で停止表示と別操作の縮む構造を保つ',
    async (width) => {
      const wrapper = mountNarrow(width)
      const section = wrapper.get('section[aria-label="送信停止と再開"]')
      const longName = 'W'.repeat(120)
      await wrapper.setProps({
        state: { gameName: longName, batter: longName, pitcher: longName },
      })

      expect(section.classes()).toContain('min-w-0')
      expect(section.get('dl').classes()).toContain('grid-cols-1')
      expect(section.get('div.grid').classes()).toContain('grid-cols-1')
      for (const card of section.findAll('dl > div')) {
        expect(card.classes()).toContain('min-w-0')
      }
      for (const button of section.findAll('button')) {
        expect(button.classes()).toContain('min-w-0')
      }
      expect(wrapper.get('main').classes()).toContain('wrap-anywhere')
      expect(wrapper.get('[data-testid="game-name"]').text()).toBe(longName)
      expect(section.text()).toContain('この端末の未確認件数')
      expect(section.text()).toContain('後続記録')
      expect(section.html()).not.toMatch(
        /\b(?:whitespace-nowrap|truncate|min-w-\[\d+px\])\b/,
      )
    },
  )
})

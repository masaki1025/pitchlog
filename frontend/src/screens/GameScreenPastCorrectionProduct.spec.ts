// @vitest-environment-options {"url":"https://pitchlog.test"}
/** 画面の選択・一時停止・保存表示を製品controller境界で照合する。 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import fixture from '../api/fixtures/lineupPrefixGame.recorded.v3.json'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import * as options from '../api/pitchTypeOptions'
import * as historyApi from '../api/lineupPrefixGame'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import type { P3TargetOffer } from '../api/pastCorrectionProduct'
import { useAuthStore } from '../stores/authStore'
import StrikeZone from '../components/zone/StrikeZone.vue'
import { GameScreenPastCorrectionProductController } from './GameScreenPastCorrectionProductController'
import GameScreenPastCorrectionProduct from './GameScreenPastCorrectionProduct.vue'
import { installUndoArtifact } from './GameScreenUndoProduct.test-support'

const game = structuredClone(fixture.value) as unknown as LineupPrefixGame
const play = game.page.items[0]!.play_row
const offer: P3TargetOffer = {
  target_reference: { game: game.id, d4: game.current_d4, d1: 1 },
  expected_version: 1,
  expected_prefix_ref: game.prefix_ref,
  target_event_id: play.source_event_id,
  target_play_id: play.id,
  original_result_id: 'batting-result.called-pitch',
}
let pinia: ReturnType<typeof createPinia>
let restoreArtifact: () => void

beforeEach(() => {
  restoreArtifact = installUndoArtifact()
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('indexedDB', {})
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: game.prefix_ref.tenantId,
    teamName: '画面試験',
  })
  vi.spyOn(
    GameScreenPastCorrectionProductController.prototype,
    'inspectPending',
  ).mockResolvedValue('ready')
  vi.spyOn(
    GameScreenPastCorrectionProductController.prototype,
    'inspect',
  ).mockResolvedValue(offer)
  vi.spyOn(options, 'readPitchTypeOptions').mockResolvedValue({
    items: [{ key: 'pitch-type.straight', display_name: '直球' }],
    next_cursor: null,
  })
})

afterEach(() => {
  restoreArtifact()
  disposePinia(pinia)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

it('実版を選び、明示差分を確定できる。一時停止中は送信せず同値復帰で入力を保持する', async () => {
  const commit = vi
    .spyOn(GameScreenPastCorrectionProductController.prototype, 'commit')
    .mockResolvedValue('pending')
  const wrapper = mount(GameScreenPastCorrectionProduct, {
    props: { game },
    global: { plugins: [pinia] },
  })
  try {
    await flushPromises()
    for (const box of wrapper.findAll('input[type="checkbox"]').slice(0, 4))
      await box.setValue(true)
    await wrapper.get('[data-testid="p3-target"]').setValue('1')
    await wrapper.get('[data-testid="p3-inspect"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="p3-result"]').exists()).toBe(true)
    await wrapper
      .get('[data-testid="p3-result"]')
      .setValue('batting-result.ball')
    expect(
      (wrapper.get('[data-testid="p3-result"]').element as HTMLSelectElement)
        .value,
    ).toBe('batting-result.ball')
    await wrapper
      .get('[data-testid="p3-pitch-type"]')
      .setValue('pitch-type.straight')
    wrapper.getComponent(StrikeZone).vm.$emit('tap', 120, 140)
    for (const box of wrapper.findAll('input[type="checkbox"]').slice(4))
      await box.setValue(true)
    await flushPromises()
    expect(
      wrapper.get('[data-testid="p3-apply"]').attributes('disabled'),
    ).toBeUndefined()
    await wrapper.setProps({ suspended: true, game: structuredClone(game) })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="p3-apply"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      (wrapper.get('[data-testid="p3-result"]').element as HTMLSelectElement)
        .value,
    ).toBe('batting-result.ball')
    await wrapper.get('[data-testid="p3-apply"]').trigger('click')
    expect(commit).not.toHaveBeenCalled()
    await wrapper.setProps({ suspended: false })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="p3-apply"]').attributes('disabled'),
    ).toBeUndefined()
    await wrapper.get('[data-testid="p3-apply"]').trigger('click')
    await flushPromises()
    expect(commit).toHaveBeenCalledOnce()
    expect(commit.mock.calls[0]?.[2].course).toEqual({
      unit: '1/263',
      x: '120',
      y: '123',
    })
    expect(wrapper.emitted('saved')).toBeUndefined()
    expect(wrapper.get('[data-testid="p3-status"]').text()).toContain(
      '結果が不明',
    )
  } finally {
    wrapper.unmount()
  }
})

it('26件目を次頁から選び、対象の実D1を照会する。混在版の頁は入力に使わない', async () => {
  const first = structuredClone(game)
  const initial = {
    ...first,
    prefix_ref: { ...first.prefix_ref, length: '26' },
    page: {
      items: Array.from({ length: 25 }, (_, index) => ({
        ...structuredClone(first.page.items[0]!),
        play_row: {
          ...first.page.items[0]!.play_row,
          id: `${String(index + 1).padStart(8, '0')}-0000-4000-8000-000000000001`,
          source_event_id: `${String(index + 1).padStart(8, '0')}-0000-4000-8000-000000000002`,
          play_number: index + 1,
        },
      })),
      next_cursor: 'next-25',
    },
  }
  const lastItem = structuredClone(initial.page.items[0]!)
  lastItem.play_row.play_number = 26
  const second = {
    ...initial,
    page: { items: [lastItem], next_cursor: null },
  }
  const read = vi
    .spyOn(historyApi, 'readLineupPrefixGame')
    .mockResolvedValue({ kind: 'found', game: second })
  const inspect = vi.mocked(
    GameScreenPastCorrectionProductController.prototype.inspect,
  )
  const wrapper = mount(GameScreenPastCorrectionProduct, {
    props: { game: initial },
    global: { plugins: [pinia] },
  })
  try {
    await flushPromises()
    for (const box of wrapper.findAll('input[type="checkbox"]').slice(0, 4))
      await box.setValue(true)
    await wrapper.get('[data-testid="p3-history-next"]').trigger('click')
    await flushPromises()
    expect(read).toHaveBeenCalledWith(game.id, 'next-25', 25)
    expect(wrapper.get('[data-testid="p3-target"]').text()).toContain('第26球')
    await wrapper.get('[data-testid="p3-target"]').setValue('26')
    await wrapper.get('[data-testid="p3-inspect"]').trigger('click')
    await flushPromises()
    expect(inspect).toHaveBeenCalledWith(26)
    read.mockResolvedValue({
      kind: 'found',
      game: { ...initial, prefix_ref: { ...initial.prefix_ref, length: '27' } },
    })
    await wrapper.get('[data-testid="p3-history-previous"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="p3-target"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('履歴頁の確定版を確認できません')
  } finally {
    wrapper.unmount()
  }
})

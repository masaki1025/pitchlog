import { shallowMount } from '@vue/test-utils'
import { nextTick, shallowRef } from 'vue'
import { expect, it, vi } from 'vitest'
import GameScreenEntryRecordHost from './GameScreenEntryRecordHost.vue'

const bindings = vi.hoisted(() => ({ retry: vi.fn(), state: null as unknown }))
vi.mock('./GameScreenEntryProvider', () => ({
  usePreparingEntryProvider: () => ({ preparing: null, retry: bindings.retry }),
}))
vi.mock('./GameScreenStartProvider', () => ({
  useGameStartProvider: () => ({ state: bindings.state }),
}))

it('開始応答保存後だけ実準備中情報を再取得し、結果不明を開始済みとしない', async () => {
  bindings.retry.mockReset()
  const state = shallowRef({ phase: 'ready' })
  bindings.state = state
  const wrapper = shallowMount(GameScreenEntryRecordHost)
  try {
    for (const phase of ['sending', 'unknown', 'failed']) {
      state.value = { phase }
      await nextTick()
      expect(bindings.retry).not.toHaveBeenCalled()
    }
    state.value = { phase: 'received' }
    await nextTick()
    expect(bindings.retry).toHaveBeenCalledOnce()
    state.value = { phase: 'received' }
    await nextTick()
    expect(bindings.retry).toHaveBeenCalledOnce()
  } finally {
    wrapper.unmount()
  }
})

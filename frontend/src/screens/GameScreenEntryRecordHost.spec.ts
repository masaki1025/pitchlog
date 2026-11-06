import { shallowMount } from '@vue/test-utils'
import { nextTick, shallowRef } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
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
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/games/:gameId/record',
        component: GameScreenEntryRecordHost,
      },
    ],
  })
  await router.push('/games/6efca380-dea3-5a4e-9749-40dfb1dbd65e/record')
  await router.isReady()
  const wrapper = shallowMount(GameScreenEntryRecordHost, {
    global: { plugins: [router] },
  })
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

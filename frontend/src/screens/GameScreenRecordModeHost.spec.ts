import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import GameScreenRecordModeHost from './GameScreenRecordModeHost.vue'
import type { LocalRecordingSession } from '../lib/localRecordingSession'
vi.mock('../lib/localRecordingSession', async (original) => ({
  ...(await original<typeof import('../lib/localRecordingSession')>()),
  isLocalRecordingSession: (value: unknown) =>
    value !== null && typeof value === 'object',
}))
describe('端末内画面からの再接続', () => {
  it('同じURLでも毎回guardを再実行し、未許可queryを認証戻り先へ追加しない', async () => {
    const gameId = '59c28087-e5d8-43e1-9e50-65833ad0cae6'
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/games/:gameId/record',
          name: 'game-record',
          component: { template: '<p />' },
        },
      ],
    })
    const guard = vi.fn(() => true)
    router.beforeEach(guard)
    await router.push({
      name: 'game-record',
      params: { gameId },
      query: { recording: 'play-prefix-v3' },
    })
    const session = {
      gameId,
      current: true,
      context: {},
      dispose: vi.fn(),
    } as unknown as LocalRecordingSession
    const wrapper = mount(GameScreenRecordModeHost, {
      props: { localSession: session },
      global: { plugins: [router], stubs: { GameScreenOrdinaryPitch: true } },
    })
    for (let index = 0; index < 2; index++) {
      await wrapper.get('button').trigger('click')
      await vi.waitFor(() => expect(guard).toHaveBeenCalledTimes(index + 2))
    }
    expect(router.currentRoute.value.query).toEqual({
      recording: 'play-prefix-v3',
    })
    wrapper.unmount()
    expect(session.dispose).toHaveBeenCalledOnce()
  })
})

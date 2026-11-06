import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import initial from '../api/fixtures/lineupPrefixGame.v3.json'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import * as viewerApi from '../api/viewerGame'
import * as rosterApi from '../api/roster'
import { installAppProviders, pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import GameScreenViewerLive from './GameScreenViewerLive.vue'

const tenant = initial.value.prefix_ref.tenantId
const gameId = initial.value.id
const head = {
  status: 'in_progress' as const,
  generation: '1',
  watermark: '0',
}
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})
it('単一pollは同版で本体を重複取得せず、通信断で旧表示を未更新へ降ろす', async () => {
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: tenant,
    teamName: '閲覧試験',
  })
  const readHead = vi.spyOn(viewerApi, 'readViewerHead').mockResolvedValue(head)
  const readGame = vi
    .spyOn(viewerApi, 'readViewerGame')
    .mockResolvedValue(initial.value as unknown as viewerApi.ViewerGame)
  vi.spyOn(rosterApi, 'getPlayer').mockRejectedValue(new Error('名簿別試験'))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/games/:gameId/view', component: GameScreenViewerLive }],
  })
  await router.push(`/games/${gameId}/view`)
  await router.isReady()
  vi.useFakeTimers()
  const wrapper = mount(GameScreenViewerLive, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  await flushPromises()
  expect(wrapper.find('[data-testid="viewer-status"]').text()).toBe('更新済み')
  expect(wrapper.text()).toContain('先攻 0 – 後攻 0')
  expect(readHead).toHaveBeenCalledTimes(1)
  expect(readGame).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(readHead).toHaveBeenCalledTimes(2)
  expect(readGame).toHaveBeenCalledTimes(1)
  readHead.mockRejectedValueOnce(new Error('通信断'))
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(wrapper.find('[data-testid="viewer-status"]').text()).toBe('未更新')
  expect(wrapper.find('[aria-label="スコア"]').exists()).toBe(false)
  wrapper.unmount()
})

it('終了済みの第3アウトは保存T2の完了半回を示し、次の10回表を開始扱いしない', async () => {
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: tenant,
    teamName: '閲覧試験',
  })
  vi.spyOn(viewerApi, 'readViewerHead').mockResolvedValue({
    ...head,
    status: 'finished',
  })
  vi.spyOn(viewerApi, 'readViewerGame').mockResolvedValue({
    ...initial.value,
    status: 'finished',
    after: {
      ...initial.value.after,
      stateFields: {
        ...initial.value.after.stateFields,
        'state.inning': '10',
        'state.half': 'top',
      },
    },
    t2: {
      kind: 'evaluated-end-condition',
      scope: 'play-prefix-v3',
      evaluation_point: 'post-play',
      facts: {
        beforeInning: '9',
        beforeHalf: 'bottom',
        beforeOuts: '2',
        afterInning: '10',
        afterHalf: 'top',
        afterOuts: '0',
        halfCompleted: true,
        outsUnchanged: false,
        scoreUnchanged: true,
        priorOpen: true,
      },
      decision: {
        outcome: 'normal-end',
        endConditionDetected: true,
        lockFurtherPlayInput: true,
        promptEndDeclaration: true,
        automaticallyEndsGame: false,
        xMark: 'recorded-score',
      },
      tiebreakStartRequired: false,
    },
  } as unknown as viewerApi.ViewerGame)
  vi.spyOn(rosterApi, 'getPlayer').mockRejectedValue(new Error('名簿名別試験'))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/games/:gameId/view', component: GameScreenViewerLive }],
  })
  await router.push(`/games/${gameId}/view`)
  await router.isReady()
  const wrapper = mount(GameScreenViewerLive, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  await flushPromises()
  expect(wrapper.find('[aria-label="スコア"]').text()).toContain('試合終了（9回裏終了）')
  expect(wrapper.find('[aria-label="スコア"]').text()).not.toContain('10回表')
  wrapper.unmount()
})

import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import initial from '../api/fixtures/lineupPrefixGame.v3.json'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import * as viewerApi from '../api/viewerGame'
import * as rosterApi from '../api/roster'
import { isGameLifecycleGame } from '../api/gameLifecycle'
import { installAppProviders, pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import { undoRead } from './GameScreenUndoProduct.test-support'
import GameScreenViewerLive from './GameScreenViewerLive.vue'

const tenant = initial.value.prefix_ref.tenantId
const gameId = initial.value.id
const head = {
  status: 'in_progress' as const,
  version: '1',
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
  await vi.advanceTimersByTimeAsync(5000)
  await flushPromises()
  expect(readHead).toHaveBeenCalledTimes(2)
  expect(readGame).toHaveBeenCalledTimes(1)
  readHead.mockRejectedValueOnce(new Error('通信断'))
  await vi.advanceTimersByTimeAsync(5000)
  await flushPromises()
  expect(wrapper.find('[data-testid="viewer-status"]').text()).toBe('未更新')
  expect(wrapper.find('[aria-label="スコア"]').exists()).toBe(false)
  wrapper.unmount()
})

it('終了済みの第3アウトは保存T2の完了半回を示し、次の10回表を開始扱いしない', async () => {
  const base = undoRead(2)
  const prior = base.checkpoint.content.restored.lastPlayEvaluation
  if (prior === null) throw new Error('既保存T2 fixtureが必要です')
  const after = {
    ...base.after,
    stateFields: {
      ...base.after.stateFields,
      'state.inning': '10',
      'state.half': 'top',
    },
  }
  const finishedGame = {
    ...base,
    status: 'finished',
    after,
    checkpoint: {
      ...base.checkpoint,
      content: {
        ...base.checkpoint.content,
        restored: {
          ...base.checkpoint.content.restored,
          current: after,
          lastPlayEvaluation: {
            ...prior,
            facts: {
              ...prior.facts,
              beforeInning: '9',
              beforeHalf: 'bottom',
              beforeOuts: '2',
              afterInning: '10',
              afterHalf: 'top',
              afterOuts: '0',
              halfCompleted: true,
            },
            decision: {
              outcome: 'normal-end',
              endConditionDetected: true,
              lockFurtherPlayInput: true,
              promptEndDeclaration: true,
              automaticallyEndsGame: false,
              xMark: 'recorded-score',
            },
          },
        },
      },
    },
    lifecycle: {
      formatVersion: 'native-game-lifecycle-read-v1',
      status: 'finished',
      lastVersion: '1',
      active: {
        version: '1',
        eventId: '33333333-3333-4333-8333-333333333333',
        receiptId: '44444444-4444-4444-8444-444444444444',
      },
      activeStatsVersionId: '55555555-5555-4555-8555-555555555555',
    },
  } as unknown as viewerApi.ViewerGame
  expect(isGameLifecycleGame(finishedGame)).toBe(true)
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamId: base.checkpoint.content.scope.tenantId,
    teamName: '閲覧試験',
  })
  vi.spyOn(viewerApi, 'readViewerHead').mockResolvedValue({
    ...head,
    status: 'finished',
    watermark: base.checkpoint.content.d3,
  })
  vi.spyOn(viewerApi, 'readViewerGame').mockResolvedValue(finishedGame)
  vi.spyOn(rosterApi, 'getPlayer').mockRejectedValue(new Error('名簿名別試験'))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/games/:gameId/view', component: GameScreenViewerLive }],
  })
  await router.push(`/games/${base.id}/view`)
  await router.isReady()
  const wrapper = mount(GameScreenViewerLive, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
  await flushPromises()
  expect(wrapper.find('[aria-label="スコア"]').text()).toContain(
    '試合終了（9回裏終了）',
  )
  expect(wrapper.find('[aria-label="スコア"]').text()).not.toContain('10回表')
  wrapper.unmount()
})

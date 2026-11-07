import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import initial from '../api/fixtures/lineupPrefixGame.v3.json'
import recorded from '../api/fixtures/lineupPrefixGame.recorded.v3.json'
import type { LineupPrefixGame } from '../api/lineupPrefixGame'
import type { ViewerGame, ViewerHead } from '../api/viewerGame'
import {
  GameScreenViewerLiveController,
  viewerLineup,
  viewerPageLabels,
  viewerPeriodLabel,
  viewerStatusLabel,
  type ViewerLiveIdentity,
  type ViewerLiveState,
} from './GameScreenViewerLiveController'

const game = initial.value as unknown as LineupPrefixGame
const saved = recorded.value as unknown as LineupPrefixGame
const tenant = initial.value.prefix_ref.tenantId
const gameId = initial.value.id
const head: ViewerHead = {
  status: 'in_progress',
  version: `ve1_${'a'.repeat(64)}`,
  watermark: '0',
}
let identity: ViewerLiveIdentity
let latest: ViewerLiveState
beforeEach(() => {
  identity = {
    authenticated: true,
    tenantId: tenant,
    authEpoch: 1,
    gameId,
  }
  latest = {
    game: null,
    head: null,
    freshness: 'loading',
    refreshing: false,
    checkedAt: null,
    pageCursors: [null],
  }
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})
function controller(
  readHead: (gameId: string, signal?: AbortSignal) => Promise<ViewerHead>,
  readGame: (
    gameId: string,
    tenantId: string,
    head: ViewerHead,
    cursor?: string | null,
    signal?: AbortSignal,
  ) => Promise<ViewerGame>,
) {
  return new GameScreenViewerLiveController(() => identity, {
    onChange: (state) => {
      latest = state
    },
    readHead,
    readGame,
    pollMs: 3000,
    staleMs: 10000,
  })
}
it('初回は版と本体を一度だけ取得し、同版pollでは本体を再取得しない', async () => {
  const readHead = vi.fn(async () => head)
  const readGame = vi.fn(async () => game)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  expect(latest.freshness).toBe('fresh')
  expect(latest.game).toBe(game)
  expect(latest.checkedAt).not.toBeNull()
  expect(readHead).toHaveBeenCalledTimes(1)
  expect(readGame).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(readHead).toHaveBeenCalledTimes(2)
  expect(readGame).toHaveBeenCalledTimes(1)
  c.stop()
})
it('poll中は更新中を示し、版変化時だけ本体を再取得する', async () => {
  let resolveHead: ((value: ViewerHead) => void) | null = null
  const readHead = vi
    .fn(async () => head)
    .mockImplementationOnce(async () => head)
    .mockImplementationOnce(
      () =>
        new Promise<ViewerHead>((resolve) => {
          resolveHead = resolve
        }),
    )
    .mockImplementation(async () => ({ ...head, watermark: '1' }))
  const readGame = vi
    .fn(async () => game)
    .mockImplementationOnce(async () => game)
    .mockImplementation(async () => saved)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(latest.refreshing).toBe(true)
  expect(viewerStatusLabel(latest.freshness, latest.refreshing)).toBe('更新中')
  resolveHead!(head)
  await flushPromises()
  expect(latest.refreshing).toBe(false)
  expect(viewerStatusLabel(latest.freshness, latest.refreshing)).toBe(
    '更新済み',
  )
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(readGame).toHaveBeenCalledTimes(2)
  expect(latest.game).toBe(saved)
  c.stop()
})
it('同水位のP3訂正を12秒pollで検知し、本文確認前は更新済みにしない', async () => {
  const corrected = {
    ...game,
    after: {
      ...game.after,
      stateFields: { ...game.after.stateFields, 'state.count.balls': '1' },
    },
  } as ViewerGame
  const revised = { ...head, version: `ve1_${'b'.repeat(64)}` }
  let resolveBody: ((value: ViewerGame) => void) | null = null
  const readHead = vi.fn(async () =>
    readHead.mock.calls.length < 5 ? head : revised,
  )
  const readGame = vi
    .fn(async () => game as ViewerGame)
    .mockImplementationOnce(async () => game)
    .mockImplementationOnce(
      () =>
        new Promise<ViewerGame>((resolve) => {
          resolveBody = resolve
        }),
    )
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  for (let index = 0; index < 4; index += 1) {
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
  }
  expect(readGame).toHaveBeenCalledTimes(2)
  expect(readGame).toHaveBeenLastCalledWith(
    gameId,
    tenant,
    revised,
    null,
    expect.any(AbortSignal),
  )
  expect(latest.game).toBeNull()
  expect(viewerStatusLabel(latest.freshness, latest.refreshing)).not.toBe(
    '更新済み',
  )
  resolveBody!(corrected)
  await flushPromises()
  expect(latest.game?.after.stateFields['state.count.balls']).toBe('1')
  expect(latest.freshness).toBe('fresh')
  expect(latest.pageCursors).toEqual([null])
  c.stop()
})
it('503は未更新として旧表示を破棄し、復帰後のpollでサーバー値へ戻る', async () => {
  const readHead = vi
    .fn(async () => head)
    .mockResolvedValueOnce(head)
    .mockRejectedValueOnce(new ApiError(503, 'unavailable', [], undefined, {}))
    .mockResolvedValueOnce(head)
  const readGame = vi.fn(async () => game)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  expect(latest.freshness).toBe('fresh')
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(latest.freshness).toBe('unupdated')
  expect(latest.game).toBeNull()
  expect(viewerStatusLabel(latest.freshness, latest.refreshing)).toBe('未更新')
  await vi.advanceTimersByTimeAsync(3000)
  await flushPromises()
  expect(latest.freshness).toBe('fresh')
  expect(latest.game).toBe(game)
  expect(readGame).toHaveBeenCalledTimes(2)
  c.stop()
})
it('不正なgame識別値は確認中のままにせず閲覧できませんへ閉じる', async () => {
  identity = { ...identity, gameId: 'not-a-uuid' }
  const readHead = vi.fn(async () => head)
  const readGame = vi.fn(async () => game)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  expect(latest.freshness).toBe('not-found')
  expect(readHead).not.toHaveBeenCalled()
  expect(readGame).not.toHaveBeenCalled()
  c.stop()
})
it('404は閲覧できません、401も未更新として区別する', async () => {
  const notFound = controller(
    vi.fn(async () => {
      throw new ApiError(404, 'not found', [], undefined, {})
    }),
    vi.fn(async () => game),
  )
  notFound.start()
  await flushPromises()
  expect(latest.freshness).toBe('not-found')
  expect(latest.game).toBeNull()
  notFound.stop()
  const unauthorized = controller(
    vi.fn(async () => {
      throw new ApiError(401, 'unauthorized', [], undefined, {})
    }),
    vi.fn(async () => game),
  )
  unauthorized.start()
  await flushPromises()
  expect(latest.freshness).toBe('unupdated')
  expect(latest.game).toBeNull()
  unauthorized.stop()
})
it('最終成功から10秒を超えたら未更新へ降ろし、遅い応答を採用しない', async () => {
  const readHead = vi
    .fn(async () => head)
    .mockResolvedValueOnce(head)
    .mockImplementation(
      () =>
        new Promise<ViewerHead>(() => {
          // 応答しない通信断を模す。
        }),
    )
  const readGame = vi.fn(async () => game)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  await vi.advanceTimersByTimeAsync(11_000)
  await flushPromises()
  expect(latest.freshness).toBe('unupdated')
  expect(latest.game).toBeNull()
  c.stop()
})
it('認証世代が変わった後の旧応答は新しい表示を上書きしない', async () => {
  let resolveOld: ((value: ViewerHead) => void) | null = null
  const readHead = vi
    .fn(async () => head)
    .mockImplementationOnce(
      () =>
        new Promise<ViewerHead>((resolve) => {
          resolveOld = resolve
        }),
    )
    .mockResolvedValueOnce(head)
  const readGame = vi.fn(async () => game)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  identity = { ...identity, authEpoch: 2 }
  c.resetAndLoad()
  await flushPromises()
  expect(latest.head?.watermark).toBe('0')
  resolveOld!({ ...head, watermark: '9' })
  await flushPromises()
  expect(latest.head?.watermark).toBe('0')
  expect(latest.game).toBe(game)
  c.stop()
})
it('履歴はcursorで1ページずつ取得し、全件を読み込まない', async () => {
  const paged = {
    ...game,
    page: { ...game.page, next_cursor: 'cursor-1' },
  } as ViewerGame
  const readHead = vi.fn(async () => head)
  const readGame = vi.fn(async () => paged)
  const c = controller(readHead, readGame)
  c.start()
  await flushPromises()
  c.nextPage()
  await flushPromises()
  expect(readGame).toHaveBeenLastCalledWith(
    gameId,
    tenant,
    head,
    'cursor-1',
    expect.any(AbortSignal),
  )
  expect(latest.pageCursors).toEqual([null, 'cursor-1'])
  c.previousPage()
  await flushPromises()
  expect(readGame).toHaveBeenLastCalledWith(
    gameId,
    tenant,
    head,
    null,
    expect.any(AbortSignal),
  )
  c.stop()
})
it('終了済みは保存T2の完了半回を表示し、lineupはclosed契約からだけ読む', () => {
  const finished = {
    ...saved,
    status: 'finished',
    after: {
      ...saved.after,
      stateFields: {
        ...saved.after.stateFields,
        'state.inning': '10',
        'state.half': 'top',
      },
    },
    t2: {
      ...saved.t2!,
      facts: {
        ...saved.t2!.facts,
        beforeInning: '9',
        beforeHalf: 'bottom',
        halfCompleted: true,
      },
      decision: { ...saved.t2!.decision, outcome: 'normal-end' },
    },
  } as unknown as ViewerGame
  expect(viewerPeriodLabel(finished)).toBe('試合終了（9回裏終了）')
  expect(viewerLineup(finished)).toBe(saved.lineup)
})

it('pagingの向きはv3と非playで取り違えない', () => {
  expect(viewerPageLabels(game)).toEqual({
    next: '古い25球へ',
    previous: '新しい25球へ',
  })
  expect(
    viewerPageLabels({ read_kind: 'nonplay-prefix' } as unknown as ViewerGame),
  ).toEqual({ next: '古い25球へ', previous: '新しい25球へ' })
})

it.each(['cold-end', 'limit-draw'] as const)(
  '完了半回のある終了は%sでも最終保存時より完了半回を表示する',
  (outcome) => {
    const finished = {
      ...saved,
      status: 'finished',
      after: {
        ...saved.after,
        stateFields: {
          ...saved.after.stateFields,
          'state.inning': '8',
          'state.half': 'top',
        },
      },
      t2: {
        ...saved.t2!,
        facts: {
          ...saved.t2!.facts,
          beforeInning: '7',
          beforeHalf: 'bottom',
          halfCompleted: true,
        },
        decision: { ...saved.t2!.decision, outcome },
      },
    } as unknown as ViewerGame
    expect(viewerPeriodLabel(finished)).toBe('試合終了（7回裏終了）')
  },
)

it('完了半回のない終了は最終保存時の回・表裏を表示する', () => {
  const finished = {
    ...saved,
    status: 'finished',
    after: {
      ...saved.after,
      stateFields: {
        ...saved.after.stateFields,
        'state.inning': '10',
        'state.half': 'top',
      },
    },
    t2: {
      ...saved.t2!,
      facts: { ...saved.t2!.facts, halfCompleted: false },
      decision: { ...saved.t2!.decision, outcome: 'walk-off' },
    },
  } as unknown as ViewerGame
  expect(viewerPeriodLabel(finished)).toBe('試合終了（最終保存時 10回表）')
})

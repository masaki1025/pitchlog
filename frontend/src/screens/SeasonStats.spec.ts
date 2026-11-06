import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  fetchSeasonStats,
  downloadSeasonStatsCsv,
  fetchGameStats,
  downloadGameStatsCsv,
  push,
} = vi.hoisted(() => ({
  fetchSeasonStats: vi.fn(),
  fetchGameStats: vi.fn(),
  downloadGameStatsCsv: vi.fn(),
  downloadSeasonStatsCsv: vi.fn(),
  push: vi.fn(),
}))

vi.mock('../api/stats', () => ({
  fetchSeasonStats,
  downloadSeasonStatsCsv,
  fetchGameStats,
  downloadGameStatsCsv,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({
    params: { gameId: '00000000-0000-4000-8000-000000000099' },
  }),
}))

import SeasonStats from './SeasonStats.vue'
import GameStatsScreen from './GameStatsScreen.vue'
import type { GameBasicStats, SeasonBasicStats } from '../api/stats'

const batting = [
  {
    metric_id: 'pa',
    label: '打席',
    state: 'available' as const,
    value: 3,
    display: '3',
    reason: null,
    components: null,
  },
]
const pitching = [
  {
    metric_id: 'appearances',
    label: '登板',
    state: 'source_unavailable' as const,
    value: null,
    display: null,
    reason: 'D03_SOURCE_PENDING',
    components: null,
  },
]
const response: SeasonBasicStats = {
  year: 2026,
  category: 'all',
  period_label: '2026年通算',
  players: [
    {
      player_id: '00000000-0000-4000-8000-000000000001',
      player_name: '山田',
      uniform_number: '7',
      team_record_id: '00000000-0000-4000-8000-000000000010',
      team_name: '自チーム',
      is_pitcher: true,
      batting,
      pitching,
      pending: ['D03_SOURCE_PENDING'],
    },
  ],
  next_cursor: null,
}

describe('SeasonStats', () => {
  beforeEach(() => {
    fetchSeasonStats.mockReset().mockResolvedValue(response)
    fetchGameStats.mockReset().mockResolvedValue(gameResponse)
    downloadSeasonStatsCsv.mockReset().mockResolvedValue({
      blob: new Blob(['x']),
      filename: 'season.csv',
    })
    push.mockReset()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:x'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('実APIの応答を既定の合算で表示し、区分切替で再取得する', async () => {
    const wrapper = mount(SeasonStats)
    await flushPromises()
    expect(fetchSeasonStats).toHaveBeenCalledWith(
      expect.any(Number),
      'all',
      expect.any(AbortSignal),
      undefined,
    )
    expect(wrapper.text()).toContain('2026年通算')
    expect(wrapper.text()).toContain('山田')
    expect(wrapper.text()).toContain('登板: 正式な投手出場sourceが未接続')

    await wrapper.find('select').setValue('official')
    await flushPromises()
    expect(fetchSeasonStats).toHaveBeenCalledWith(
      expect.any(Number),
      'official',
      expect.any(AbortSignal),
      undefined,
    )
  })

  it('CSVを取得してobject URLを解除する', async () => {
    const wrapper = mount(SeasonStats)
    await flushPromises()
    const button = wrapper
      .findAll('button')
      .find((item) => item.text() === 'CSVダウンロード')
    expect(button).toBeDefined()
    await button?.trigger('click')
    await flushPromises()
    expect(downloadSeasonStatsCsv).toHaveBeenCalledWith(
      expect.any(Number),
      'all',
    )
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:x')
  })
})

const gameResponse: GameBasicStats = {
  game_id: '00000000-0000-4000-8000-000000000099',
  mode: 'current',
  players: response.players,
  next_cursor: null,
}

function playerAt(index: number) {
  return {
    ...response.players[0]!,
    player_id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    player_name: `${index}番`,
  }
}

describe('成績ページの境界と非同期条件', () => {
  it('シーズンの201人目を次ページに出し、CSVは同じ条件で取得する', async () => {
    const cursor = '00000000-0000-4000-8000-000000000200'
    fetchSeasonStats
      .mockResolvedValueOnce({
        ...response,
        players: Array.from({ length: 200 }, (_, i) => playerAt(i + 1)),
        next_cursor: cursor,
      })
      .mockResolvedValueOnce({
        ...response,
        players: [playerAt(201)],
        next_cursor: null,
      })
    const wrapper = mount(SeasonStats)
    await flushPromises()
    expect(wrapper.text()).toContain('1–200名を表示中')
    expect(wrapper.text()).not.toContain('201番')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '次へ')
      ?.trigger('click')
    await flushPromises()
    expect(fetchSeasonStats).toHaveBeenLastCalledWith(
      expect.any(Number),
      'all',
      expect.any(AbortSignal),
      cursor,
    )
    expect(wrapper.text()).toContain('201番')
    expect(wrapper.text()).toContain('201–201名を表示中')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'CSVダウンロード')
      ?.trigger('click')
    await flushPromises()
    expect(downloadSeasonStatsCsv).toHaveBeenCalledWith(
      expect.any(Number),
      'all',
    )
  })

  it('試合の201人目を次ページに出す', async () => {
    const cursor = '00000000-0000-4000-8000-000000000200'
    fetchGameStats
      .mockResolvedValueOnce({
        ...gameResponse,
        players: Array.from({ length: 200 }, (_, i) => playerAt(i + 1)),
        next_cursor: cursor,
      })
      .mockResolvedValueOnce({
        ...gameResponse,
        players: [playerAt(201)],
        next_cursor: null,
      })
    const wrapper = mount(GameStatsScreen)
    await flushPromises()
    expect(wrapper.text()).toContain('1–200名を表示中')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '次へ')
      ?.trigger('click')
    await flushPromises()
    expect(fetchGameStats).toHaveBeenLastCalledWith(
      gameResponse.game_id,
      'current',
      expect.any(AbortSignal),
      cursor,
    )
    expect(wrapper.text()).toContain('201番')
    expect(wrapper.text()).toContain('201–201名を表示中')
  })

  it('シーズン切替中の古い応答を破棄する', async () => {
    let resolveOld!: (value: SeasonBasicStats) => void
    fetchSeasonStats
      .mockImplementationOnce(
        () =>
          new Promise<SeasonBasicStats>((resolve) => {
            resolveOld = resolve
          }),
      )
      .mockResolvedValueOnce({
        ...response,
        category: 'official',
        players: [playerAt(2)],
      })
    const wrapper = mount(SeasonStats)
    await flushPromises()
    await wrapper.find('select').setValue('official')
    await flushPromises()
    resolveOld({ ...response, players: [playerAt(1)] })
    await flushPromises()
    expect(wrapper.text()).toContain('2番')
    expect(wrapper.text()).not.toContain('1番')
    expect(wrapper.text()).toContain('公式')
  })

  it('試合モード切替中の古い応答を破棄する', async () => {
    let resolveOld!: (value: GameBasicStats) => void
    fetchGameStats
      .mockImplementationOnce(
        () =>
          new Promise<GameBasicStats>((resolve) => {
            resolveOld = resolve
          }),
      )
      .mockResolvedValueOnce({
        ...gameResponse,
        mode: 'official',
        players: [playerAt(2)],
      })
    const wrapper = mount(GameStatsScreen)
    await flushPromises()
    await wrapper.find('select').setValue('official')
    await flushPromises()
    resolveOld({ ...gameResponse, players: [playerAt(1)] })
    await flushPromises()
    expect(wrapper.text()).toContain('2番')
    expect(wrapper.text()).not.toContain('1番')
  })
})

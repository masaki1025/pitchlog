import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { fetchSeasonStats, downloadSeasonStatsCsv, push } = vi.hoisted(() => ({
  fetchSeasonStats: vi.fn(),
  downloadSeasonStatsCsv: vi.fn(),
  push: vi.fn(),
}))

vi.mock('../api/stats', () => ({
  fetchSeasonStats,
  downloadSeasonStatsCsv,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

import SeasonStats from './SeasonStats.vue'
import type { SeasonBasicStats } from '../api/stats'

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
    expect(fetchSeasonStats).toHaveBeenCalledWith(expect.any(Number), 'all')
    expect(wrapper.text()).toContain('2026年通算')
    expect(wrapper.text()).toContain('山田')
    expect(wrapper.text()).toContain('登板: 正式な投手出場sourceが未接続')

    await wrapper.find('select').setValue('official')
    await flushPromises()
    expect(fetchSeasonStats).toHaveBeenCalledWith(
      expect.any(Number),
      'official',
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

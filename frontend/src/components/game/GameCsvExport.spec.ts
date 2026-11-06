import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/client'

const downloadPlayCsv = vi.hoisted(() => vi.fn())
vi.mock('../../api/gameExports', () => ({ downloadPlayCsv }))

import GameCsvExport from './GameCsvExport.vue'

describe('GameCsvExport', () => {
  beforeEach(() => {
    downloadPlayCsv.mockReset()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:zip'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('長さ一致後にだけ保存し、object URLを解除する', async () => {
    downloadPlayCsv.mockResolvedValue({
      blob: new Blob(['zipdata']),
      filename: 'plays.zip',
      contentLength: 7,
      sha256: null,
    })
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    const button = wrapper.find('button')
    await button.trigger('click')
    await flushPromises()
    expect(downloadPlayCsv).toHaveBeenCalledTimes(1)
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:zip')
    expect(wrapper.text()).toContain('毎球CSVを保存しました')
  })

  it('長さ不一致は保存せず、失敗を表示する', async () => {
    downloadPlayCsv.mockResolvedValue({
      blob: new Blob(['zipdata']),
      filename: 'plays.zip',
      contentLength: 99,
      sha256: null,
    })
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('長さまたはSHA-256が一致しない')
  })

  it('409の未供給を表示し、再試行できる', async () => {
    downloadPlayCsv.mockRejectedValueOnce(
      new ApiError(
        409,
        '供給不足',
        [{ location: 'plays_csv.columns.34' }],
        undefined,
        null,
      ),
    )
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('供給が不足')
    expect(wrapper.text()).toContain('plays_csv.columns.34')
    expect(wrapper.findAll('button')[1]?.text()).toBe('再試行')
  })

  it('取得中の二重押下を1回に閉じる', async () => {
    let resolve: (value: unknown) => void = () => undefined
    downloadPlayCsv.mockReturnValue(
      new Promise((done) => {
        resolve = done
      }),
    )
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    const button = wrapper.find('button')
    await button.trigger('click')
    await button.trigger('click')
    expect(downloadPlayCsv).toHaveBeenCalledTimes(1)
    resolve({
      blob: new Blob(['zipdata']),
      filename: 'plays.zip',
      contentLength: null,
      sha256: null,
    })
    await flushPromises()
  })
})

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Blob as NodeBlob } from 'node:buffer'
import { webcrypto } from 'node:crypto'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../../stores/authStore'
import { setVerifiedAuthForTest } from '../../api/auth.test-support'
import { ApiError } from '../../api/client'

const downloadPlayCsv = vi.hoisted(() => vi.fn())
vi.mock('../../api/gameExports', () => ({ downloadPlayCsv }))

import GameCsvExport from './GameCsvExport.vue'

const SHA = 'a1b8b2250981a957cb59f74e9a9eb9f019e94e7e50d28596f6a927112b1ca256'

describe('GameCsvExport', () => {
  afterEach(() => vi.unstubAllGlobals())
  beforeEach(() => {
    downloadPlayCsv.mockReset()
    localStorage.clear()
    setActivePinia(createPinia())
    setVerifiedAuthForTest(useAuthStore(), {
      teamName: '試験',
      teamId: '6efca380-dea3-5a4e-9749-40dfb1dbd65e',
    })
    vi.stubGlobal('Blob', NodeBlob)
    vi.stubGlobal('crypto', webcrypto)
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:zip'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('長さと真正SHA一致後にだけ保存し、object URLを解除する', async () => {
    downloadPlayCsv.mockResolvedValue({
      blob: new Blob(['zipdata']),
      filename: 'plays.zip',
      contentLength: 7,
      sha256: SHA,
    })
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    const button = wrapper.find('button')
    await button.trigger('click')
    await flushPromises()
    expect(downloadPlayCsv).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => expect(URL.createObjectURL).toHaveBeenCalled())
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
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('長さまたはSHA-256が一致しない'),
    )
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
  it.each([
    { contentLength: null, sha256: null },
    { contentLength: null, sha256: SHA },
    { contentLength: 7, sha256: null },
    { contentLength: 7, sha256: 'not-a-digest' },
    { contentLength: 7, sha256: '0'.repeat(64) },
    { contentLength: Number.NaN, sha256: SHA },
    { contentLength: Number.POSITIVE_INFINITY, sha256: SHA },
    { contentLength: 7.1, sha256: SHA },
    { contentLength: -1, sha256: SHA },
  ])('必須metadata欠落・不正・SHA不一致を保存しない: %j', async (metadata) => {
    downloadPlayCsv.mockResolvedValue({
      blob: new Blob(['zipdata']),
      filename: 'plays.zip',
      ...metadata,
    })
    const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('長さまたはSHA-256が一致しない'),
    )
  })

  it.each(['unmount', 'game-change', 'auth-change'])(
    '取得後の%sでは旧ZIPを保存しない',
    async (change) => {
      let resolve!: (value: unknown) => void
      downloadPlayCsv.mockReturnValue(
        new Promise((done) => {
          resolve = done
        }),
      )
      const wrapper = mount(GameCsvExport, { props: { gameId: 'game-1' } })
      await wrapper.find('button').trigger('click')
      if (change === 'unmount') wrapper.unmount()
      if (change === 'game-change') await wrapper.setProps({ gameId: 'game-2' })
      if (change === 'auth-change') useAuthStore().authEpoch += 1
      resolve({
        blob: new Blob(['zipdata']),
        filename: 'plays.zip',
        contentLength: 7,
        sha256: SHA,
      })
      await flushPromises()
      expect(URL.createObjectURL).not.toHaveBeenCalled()
    },
  )
})

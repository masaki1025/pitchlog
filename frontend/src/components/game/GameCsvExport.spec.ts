import { setVerifiedAuthForTest } from '../../api/auth.test-support'
import { ApiError, ApiNetworkError, ApiStaleAuthError } from '../../api/client'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../stores/authStore'
import GameCsvExport from './GameCsvExport.vue'

const bindings = vi.hoisted(() => ({
  download: vi.fn(),
  verify: vi.fn(),
  verificationError: class extends Error {},
}))

vi.mock('../../api/gameExports', () => ({
  downloadGamePlayCsv: bindings.download,
  verifyGamePlayArchive: bindings.verify,
  GameExportVerificationError: bindings.verificationError,
}))

const GAME = '6efca380-dea3-5a4e-9749-40dfb1dbd65e'
const TEAM = '62dd5c6b-356d-5374-aa7e-9ea4c88c58ce'

let pinia: Pinia
let createObjectURL: ReturnType<typeof vi.fn>
let revokeObjectURL: ReturnType<typeof vi.fn>

function downloaded() {
  const blob = new Blob(['zip'])
  return {
    blob,
    filename: 'pitchlog-plays.zip',
    contentLength: blob.size,
    sha256: 'a'.repeat(64),
  }
}

function mountExport(unsentCount?: number) {
  return mount(GameCsvExport, {
    props: { gameId: GAME, unsentCount },
  })
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(pinia), {
    teamName: '検証済み試験チーム',
    teamId: TEAM,
  })
  bindings.download.mockReset()
  bindings.verify.mockReset()
  createObjectURL = vi.fn(() => 'blob:test')
  revokeObjectURL = vi.fn()
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: createObjectURL,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: revokeObjectURL,
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  disposePinia(pinia)
})

describe('GameCsvExport', () => {
  it('長さとSHA256の検証後だけ保存し、object URLを解除する', async () => {
    vi.useFakeTimers()
    const archive = downloaded()
    bindings.download.mockResolvedValue(archive)
    bindings.verify.mockResolvedValue({
      blob: archive.blob,
      filename: archive.filename,
      sha256: archive.sha256,
    })
    const wrapper = mountExport(2)

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(bindings.download).toHaveBeenCalledWith(GAME, {
      signal: expect.any(AbortSignal),
    })
    expect(bindings.verify).toHaveBeenCalledWith(archive)
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('ZIPを保存しました')
    expect(wrapper.text()).toContain('未送信が2件あります')
    vi.runAllTimers()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test')
  })

  it('検証失敗ではanchorを押さず再試行可能な失敗にする', async () => {
    bindings.download.mockResolvedValue(downloaded())
    bindings.verify.mockRejectedValue(
      new bindings.verificationError('完成ZIPのSHA256が一致しません'),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('ZIPを保存できませんでした')
    expect(wrapper.text()).toContain('SHA256が一致しません')
    expect(wrapper.text()).toContain('再試行')
  })

  it('409の欠測列数を表示し、404は再試行させない', async () => {
    bindings.download.mockRejectedValueOnce(
      new ApiError(
        409,
        '供給不足',
        [{ location: 'missing_column.34.球数.G04-A' }],
        undefined,
        undefined,
      ),
    )
    const wrapper = mountExport()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('不足列 1 件')
    expect(wrapper.text()).toContain('再試行')

    bindings.download.mockRejectedValueOnce(
      new ApiError(404, 'not found', [], undefined, undefined),
    )
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('この試合は出力できません')
    expect(wrapper.text()).not.toContain('再試行')
  })

  it('取消では保存せず、取消状態を表示する', async () => {
    bindings.download.mockImplementation(
      (_gameId: string, options: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          options.signal.addEventListener('abort', () => {
            const error = new Error('aborted')
            error.name = 'AbortError'
            reject(error)
          })
        }),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    await wrapper.get('button:nth-of-type(2)').trigger('click')
    await flushPromises()

    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('ダウンロードを取り消しました')
  })

  it('二重押下では同時に2回取得しない', async () => {
    let resolve!: (value: ReturnType<typeof downloaded>) => void
    bindings.download.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        }),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    await wrapper.get('button').trigger('click')
    expect(bindings.download).toHaveBeenCalledOnce()
    resolve(downloaded())
    bindings.verify.mockResolvedValue({
      blob: new Blob(['zip']),
      filename: 'pitchlog-plays.zip',
      sha256: 'a'.repeat(64),
    })
    await flushPromises()
  })

  it('取得中に認証世代が変わったら保存しない', async () => {
    const auth = useAuthStore(pinia)
    let resolve!: (value: ReturnType<typeof downloaded>) => void
    bindings.download.mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done
        }),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    auth.authEpoch += 1
    resolve(downloaded())
    await flushPromises()

    expect(bindings.verify).not.toHaveBeenCalled()
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('認証が切り替わったため保存しません')
  })

  it('ネットワーク不明は保存未確認として再試行を出す', async () => {
    bindings.download.mockRejectedValue(
      new ApiNetworkError(new Error('offline')),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('保存できたか確認できない')
    expect(wrapper.text()).toContain('再試行')
  })

  it('stale応答は再試行ではなくログイン確認を促す', async () => {
    bindings.download.mockRejectedValue(
      new ApiStaleAuthError('GET', '/games/x/exports/plays.zip', 200),
    )
    const wrapper = mountExport()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('ログイン状態を確認して再試行')
    expect(
      wrapper.findAll('button').map((button) => button.text()),
    ).not.toContain('再試行')
  })
})

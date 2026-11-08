/** 頁境界の試験補助は数学を再計算せず、原本全値を保持する。 */
import { describe, expect, it, vi } from 'vitest'
import { recordedBattedRow } from './BattedBatchPaging.e2e-support'

const row = (n: number) => ({
  play_row: { id: `saved-${n}`, play_number: n },
  physical: { before: n },
})
const page = (start: number, end: number, next: string | null) => ({
  prefix_ref: { length: '59', generation: 'original' },
  after: { score: { away: '2', home: '0' }, flags: [true, false] },
  roster: { players: ['original-player'] },
  last_source: { event: 'original-source' },
  page: {
    items: Array.from({ length: end - start + 1 }, (_, i) => row(start + i)),
    next_cursor: next,
  },
})

describe('同版25件頁から保存済みplayを一意に取得', () => {
  it.each([26, 51, 59])('%i件目を最大3頁から全値のまま取得', async (target) => {
    const first = page(1, 25, 'next-25')
    const second = page(26, 50, 'next-50')
    const third = page(51, 59, null)
    const read = vi.fn(async (cursor: string) =>
      cursor === 'next-25' ? second : third,
    )
    expect(await recordedBattedRow(first, target, read)).toEqual(row(target))
    expect(read.mock.calls).toEqual([['next-25'], ['next-50']])
  })
  it('最初の25件内でも後頁の重複targetを拒否', async () => {
    const first = page(1, 25, 'next')
    const second = page(25, 26, null)
    await expect(
      recordedBattedRow(first, 25, async () => second),
    ).rejects.toThrow('重複')
  })
  it('反復cursorを拒否し同頁を再送しない', async () => {
    const read = vi.fn(async () => page(26, 50, 'next'))
    await expect(
      recordedBattedRow(page(1, 25, 'next'), 26, read),
    ).rejects.toThrow('cursor')
    expect(read).toHaveBeenCalledTimes(1)
  })
  it.each(['prefix_ref', 'after', 'roster', 'last_source'] as const)(
    '%sの版差替えを拒否',
    async (key) => {
      const second = page(26, 50, null)
      const changed = {
        ...second,
        [key]: { changed: true },
      } as unknown as typeof second
      await expect(
        recordedBattedRow(page(1, 25, 'next'), 26, async () => changed),
      ).rejects.toThrow('全head')
    },
  )
  it('3頁後もcursorが残る場合は4頁目を読まない', async () => {
    const read = vi.fn(async (cursor: string) =>
      cursor === 'next25' ? page(26, 50, 'next50') : page(51, 59, 'next59'),
    )
    await expect(
      recordedBattedRow(page(1, 25, 'next25'), 51, read),
    ).rejects.toThrow('最大3頁')
    expect(read).toHaveBeenCalledTimes(2)
  })
  it('target欠測を補完しない', async () => {
    await expect(
      recordedBattedRow(page(1, 25, null), 26, async () => page(26, 26, null)),
    ).rejects.toThrow('一意')
  })
})

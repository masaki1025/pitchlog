import { expect, it } from 'vitest'
import { readP3ScreenTarget } from './p3PagingScreenEvidence'

function page(first: number, last: number, cursor: string | null) {
  return {
    prefix_ref: { historyVersion: '1', digest: 'same' },
    after: { balls: '1' },
    page: {
      items: Array.from({ length: last - first + 1 }, (_, index) => ({
        play_row: {
          id: `play-${first + index}`,
          source_event_id: `event-${first + index}`,
          play_number: first + index,
        },
      })),
      next_cursor: cursor,
    },
  }
}
it('26件目を同版の次頁から実IDで取得する', async () => {
  const head = page(1, 25, 'second')
  expect(
    (await readP3ScreenTarget(head, 26, 26, async () => page(26, 26, null)))
      .play_row.id,
  ).toBe('play-26')
})
it('三球モードは旧一頁のままで全件を確認する', async () => {
  expect(
    (
      await readP3ScreenTarget(page(1, 3, null), 3, 3, async () => {
        throw new Error('unused')
      })
    ).play_row.play_number,
  ).toBe(3)
})
for (const fault of ['mixed', 'missing', 'duplicate', 'extra-page'] as const)
  it(`${fault}を件数や対象一致だけで成功にしない`, async () => {
    const head = page(1, 25, 'second')
    const tail = page(26, 26, null)
    if (fault === 'mixed') tail.after.balls = '2'
    if (fault === 'missing') tail.page.items = []
    if (fault === 'duplicate')
      tail.page.items[0]!.play_row.source_event_id = 'event-1'
    if (fault === 'extra-page') tail.page.next_cursor = 'third'
    await expect(
      readP3ScreenTarget(head, 26, 26, async () => tail),
    ).rejects.toThrow()
  })

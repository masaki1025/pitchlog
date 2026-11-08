import { afterEach, expect, it, vi } from 'vitest'
import fixture from '../api/fixtures/lineupPrefixGame.recorded.v3.json'
import * as api from '../api/lineupPrefixGame'
import {
  completeP3HistoryPage,
  readP3TargetPage,
} from './pastCorrectionHistoryPage'

function page(
  first: number,
  count: number,
  next: string | null,
): api.LineupPrefixGame {
  const game = structuredClone(fixture.value) as unknown as api.LineupPrefixGame
  return {
    ...game,
    prefix_ref: { ...game.prefix_ref, length: '26' },
    page: {
      items: Array.from({ length: count }, (_, index) => ({
        ...structuredClone(game.page.items[0]!),
        play_row: {
          ...game.page.items[0]!.play_row,
          id: `${String(first + index).padStart(8, '0')}-0000-4000-8000-000000000001`,
          source_event_id: `${String(first + index).padStart(8, '0')}-0000-4000-8000-000000000002`,
          play_number: first + index,
        },
      })),
      next_cursor: next,
    },
  }
}

afterEach(() => vi.restoreAllMocks())

it.each([1, 25, 26])(
  '対象D1=%iの頁だけを返し、各GETを25件に保つ',
  async (d1) => {
    const read = vi
      .spyOn(api, 'readLineupPrefixGame')
      .mockImplementation(async (_id, cursor) => ({
        kind: 'found',
        game: cursor === null ? page(1, 25, 'cursor-25') : page(26, 1, null),
      }))
    const assertIdentity = vi.fn()
    const result = await readP3TargetPage(fixture.value.id, d1, assertIdentity)
    expect(result.target.play_row.play_number).toBe(d1)
    expect(result.game.page.items).toHaveLength(d1 === 26 ? 1 : 25)
    expect(read.mock.calls).toEqual(
      d1 === 26
        ? [
            [fixture.value.id, null, 25],
            [fixture.value.id, 'cursor-25', 25],
          ]
        : [[fixture.value.id, null, 25]],
    )
    expect(assertIdentity).toHaveBeenCalledTimes(read.mock.calls.length)
  },
)

it.each([
  'missing',
  'extra',
  'early-end',
  'empty',
  'mixed-head',
  'repeated-cursor',
])('%sを成功した対象頁へ昇格しない', async (failure) => {
  vi.spyOn(api, 'readLineupPrefixGame').mockImplementation(
    async (_id, cursor) => {
      let value = cursor === null ? page(1, 25, 'cursor-25') : page(26, 1, null)
      if (cursor === null && failure === 'missing')
        value = page(1, 24, 'cursor-25')
      if (cursor === null && failure === 'extra') value = page(1, 26, null)
      if (cursor === null && failure === 'early-end') value = page(1, 25, null)
      if (cursor !== null && failure === 'empty') value = page(26, 0, null)
      if (cursor !== null && failure === 'mixed-head')
        value = {
          ...value,
          prefix_ref: {
            ...value.prefix_ref,
            checkpoint: {
              ...value.prefix_ref.checkpoint,
              digest: 'b'.repeat(64),
            },
          },
        }
      if (cursor !== null && failure === 'repeated-cursor')
        value = page(26, 1, 'cursor-25')
      return { kind: 'found', game: value }
    },
  )
  await expect(
    readP3TargetPage(fixture.value.id, 26, () => {}),
  ).rejects.toThrow()
})

it('認証変更は次頁の対象採用前に拒否する', async () => {
  vi.spyOn(api, 'readLineupPrefixGame').mockImplementation(
    async (_id, cursor) => ({
      kind: 'found',
      game: cursor === null ? page(1, 25, 'cursor-25') : page(26, 1, null),
    }),
  )
  const assertIdentity = vi
    .fn()
    .mockImplementationOnce(() => {})
    .mockImplementation(() => {
      throw Error('identity changed')
    })
  await expect(
    readP3TargetPage(fixture.value.id, 26, assertIdentity),
  ).rejects.toThrow('identity changed')
})

it('確定水位を越える対象や非整数を取得済みの別行で代用しない', async () => {
  vi.spyOn(api, 'readLineupPrefixGame').mockResolvedValue({
    kind: 'found',
    game: page(1, 25, 'cursor-25'),
  })
  for (const d1 of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1, 27])
    await expect(
      readP3TargetPage(fixture.value.id, d1, () => {}),
    ).rejects.toThrow()
  expect(completeP3HistoryPage(page(1, 25, 'cursor-25'), 0)).toBe(false)
})

it.each([
  'shifted',
  'swapped',
  'duplicate-position',
  'duplicate-event',
  'duplicate-play',
])('%sの行をD1ラベルへ推定しない', (failure) => {
  const value = page(1, 25, 'cursor-25')
  const a = { ...value.page.items[0]!.play_row }
  const b = { ...value.page.items[1]!.play_row }
  if (failure === 'shifted') a.play_number = 2
  if (failure === 'swapped') {
    a.play_number = 2
    b.play_number = 1
  }
  if (failure === 'duplicate-position') b.play_number = 1
  if (failure === 'duplicate-event') b.source_event_id = a.source_event_id
  if (failure === 'duplicate-play') b.id = a.id
  expect(
    completeP3HistoryPage(
      {
        ...value,
        page: {
          ...value.page,
          items: value.page.items.map((item, index) => ({
            ...item,
            play_row: index === 0 ? a : index === 1 ? b : item.play_row,
          })),
        },
      },
      1,
    ),
  ).toBe(false)
})

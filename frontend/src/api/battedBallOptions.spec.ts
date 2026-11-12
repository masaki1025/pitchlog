import { beforeEach, expect, it, vi } from 'vitest'
import * as client from './client'
import {
  cachedBattedBallOptions,
  clearBattedBallOptionsCache,
  readBattedBallOptions,
  rememberBattedBallOptions,
} from './battedBallOptions'
beforeEach(() => vi.restoreAllMocks())
it('C2 tenant照合を使い1ページだけ取得する', async () => {
  const call = vi.spyOn(client, 'apiRequest').mockResolvedValue({
    items: [{ key: 'pitch.a', display_name: '打球語彙A' }],
    next_cursor: 'cGl0Y2guYQ',
  })
  expect(await readBattedBallOptions(null, 1)).toEqual({
    items: [{ key: 'pitch.a', display_name: '打球語彙A' }],
    next_cursor: 'cGl0Y2guYQ',
  })
  expect(call).toHaveBeenCalledWith('GET', '/vocabularies/batted-balls', {
    tenantBound: true,
    query: { limit: 1 },
    signal: undefined,
  })
  expect(call).toHaveBeenCalledOnce()
})
it('不正shape・重複key・空ページのcursorを拒否する', async () => {
  const call = vi.spyOn(client, 'apiRequest')
  for (const p of [
    {
      items: [
        { key: 'pitch.a', display_name: 'A' },
        { key: 'pitch.a', display_name: 'duplicate' },
      ],
      next_cursor: null,
    },
    { items: [], next_cursor: 'pitch.b' },
    {
      items: [{ key: 'pitch.b', display_name: 'B', tenant_id: 'other' }],
      next_cursor: null,
    },
    { items: [], next_cursor: null, extra: true },
  ]) {
    call.mockResolvedValueOnce(p)
    await expect(readBattedBallOptions('pitch.a', 1)).rejects.toThrow()
  }
})
it('limit不正ではHTTPを呼ばない', async () => {
  const call = vi.spyOn(client, 'apiRequest')
  for (const limit of [0, 101, 1.5, NaN])
    await expect(readBattedBallOptions(null, limit)).rejects.toThrow()
  expect(call).not.toHaveBeenCalled()
})

it('BE正規base64url cursorを不透明に往復し、生keyと比較しない', async () => {
  // games.encode_preparation_options_cursorのUTF-8 key / base64url(no padding)と同じ固定値。
  const cursor = 'cGl0Y2guYQ'
  const call = vi
    .spyOn(client, 'apiRequest')
    .mockResolvedValueOnce({
      items: [{ key: 'pitch.a', display_name: 'A' }],
      next_cursor: cursor,
    })
    .mockResolvedValueOnce({
      items: [{ key: 'pitch.b', display_name: 'B' }],
      next_cursor: null,
    })
  const first = await readBattedBallOptions(null, 1)
  expect(first.next_cursor).toBe(cursor)
  expect(await readBattedBallOptions(first.next_cursor, 1)).toEqual({
    items: [{ key: 'pitch.b', display_name: 'B' }],
    next_cursor: null,
  })
  expect(call.mock.calls[1]![2]?.query).toEqual({ limit: 1, cursor })
})
it('同一cursorの再掲を拒否し、opaqueな値の順序を推測しない', async () => {
  const cursor = 'cGl0Y2guYQ'
  vi.spyOn(client, 'apiRequest').mockResolvedValue({
    items: [{ key: 'pitch.b', display_name: 'B' }],
    next_cursor: cursor,
  })
  await expect(readBattedBallOptions(cursor, 1)).rejects.toThrow()
})

it('同一tenantの先頭ページだけをキャッシュし、次ページは覚えない', () => {
  clearBattedBallOptionsCache()
  const first = {
    items: [{ key: 'pitch.a', display_name: 'A' }],
    next_cursor: null,
  }
  rememberBattedBallOptions('tenant/1', first)
  expect(cachedBattedBallOptions('tenant/1')).toEqual(first)
  rememberBattedBallOptions('tenant/2', {
    items: [{ key: 'pitch.b', display_name: 'B' }],
    next_cursor: 'next',
  })
  expect(cachedBattedBallOptions('tenant/2')).toBeNull()
  clearBattedBallOptionsCache()
  expect(cachedBattedBallOptions('tenant/1')).toBeNull()
})

it('先頭ページは5分で失効し、保持件数は8件に制限する', () => {
  clearBattedBallOptionsCache()
  const now = vi.spyOn(Date, 'now').mockReturnValue(1_000)
  const page = {
    items: [{ key: 'pitch.a', display_name: 'A' }],
    next_cursor: null,
  }
  rememberBattedBallOptions('tenant/1', page)
  expect(cachedBattedBallOptions('tenant/1')).toEqual(page)
  now.mockReturnValue(1_000 + 5 * 60 * 1000 + 1)
  expect(cachedBattedBallOptions('tenant/1')).toBeNull()
  for (let index = 0; index < 9; index += 1) {
    now.mockReturnValue(10_000 + index)
    rememberBattedBallOptions(`tenant/${index}`, {
      items: [{ key: `pitch.${index}`, display_name: String(index) }],
      next_cursor: null,
    })
  }
  expect(cachedBattedBallOptions('tenant/0')).toBeNull()
  expect(cachedBattedBallOptions('tenant/1')).not.toBeNull()
  expect(cachedBattedBallOptions('tenant/8')).not.toBeNull()
})

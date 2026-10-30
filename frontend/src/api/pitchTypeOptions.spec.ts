import { beforeEach, expect, it, vi } from 'vitest'
import * as client from './client'
import { readPitchTypeOptions } from './pitchTypeOptions'
beforeEach(() => vi.restoreAllMocks())
it('C2 tenant照合を使い1ページだけ取得する', async () => {
  const call = vi.spyOn(client, 'apiRequest').mockResolvedValue({
    items: [{ key: 'pitch.a', display_name: '球種A' }],
    next_cursor: 'cGl0Y2guYQ',
  })
  expect(await readPitchTypeOptions(null, 1)).toEqual({
    items: [{ key: 'pitch.a', display_name: '球種A' }],
    next_cursor: 'cGl0Y2guYQ',
  })
  expect(call).toHaveBeenCalledWith('GET', '/vocabularies/pitch-types', {
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
    await expect(readPitchTypeOptions('pitch.a', 1)).rejects.toThrow()
  }
})
it('limit不正ではHTTPを呼ばない', async () => {
  const call = vi.spyOn(client, 'apiRequest')
  for (const limit of [0, 101, 1.5, NaN])
    await expect(readPitchTypeOptions(null, limit)).rejects.toThrow()
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
  const first = await readPitchTypeOptions(null, 1)
  expect(first.next_cursor).toBe(cursor)
  expect(await readPitchTypeOptions(first.next_cursor, 1)).toEqual({
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
  await expect(readPitchTypeOptions(cursor, 1)).rejects.toThrow()
})

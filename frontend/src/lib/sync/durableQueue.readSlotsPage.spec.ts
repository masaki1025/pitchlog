import 'fake-indexeddb/auto'
import { afterEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBObjectStore } from 'fake-indexeddb'
import {
  openDurableQueue,
  DURABLE_QUEUE_PUBLIC_METHOD_RULES,
  type DurableQueue,
} from './durableQueue'
const handles: DurableQueue[] = []
async function queue() {
  const q = await openDurableQueue({
    databaseName: 'finite-keyset-read',
    indexedDbFactory: new IDBFactory(),
    requestStoragePersistence: async () => false,
  })
  handles.push(q)
  return q
}
afterEach(() => {
  handles.splice(0).forEach((q) => q.close())
  vi.restoreAllMocks()
})
it('既複合PKのgame/D4/D1順でlimit+1/keysetを読み、他scopeとcounterを変更しない', async () => {
  const q = await queue(),
    scope = { game: 'game-a', d4: 'generation-a' }
  for (let n = 1; n <= 3; n++)
    await q.append(
      q.prepareAppend({
        scope,
        d5: 'operation-' + n,
        version: 1,
        event: { fields: { V7: { n } } },
      }),
    )
  await q.append(
    q.prepareAppend({
      scope: { game: 'game-a', d4: 'generation-b' },
      d5: 'other',
      version: 1,
      event: { fields: {} },
    }),
  )
  await q.append(
    q.prepareAppend({
      scope: { game: 'game-b', d4: 'generation-a' },
      d5: 'other',
      version: 1,
      event: { fields: {} },
    }),
  )
  const add = vi.spyOn(IDBObjectStore.prototype, 'add'),
    put = vi.spyOn(IDBObjectStore.prototype, 'put'),
    clear = vi.spyOn(IDBObjectStore.prototype, 'clear'),
    remove = vi.spyOn(IDBObjectStore.prototype, 'delete')
  const first = await q.readSlotsPage(scope, null, 2)
  expect(first.items.map((s) => s.d1)).toEqual([1, 2])
  expect(first.nextCursorD1).toBe(2)
  const second = await q.readSlotsPage(scope, first.nextCursorD1, 2)
  expect(second.items.map((s) => s.d1)).toEqual([3])
  expect(second.nextCursorD1).toBeNull()
  expect(await q.readSlotsPage(scope, 3, 2)).toEqual({
    items: [],
    nextCursorD1: null,
  })
  expect(await q.readNextD1(scope)).toBe(4)
  for (const spy of [add, put, clear, remove])
    expect(spy).not.toHaveBeenCalled()
  expect(DURABLE_QUEUE_PUBLIC_METHOD_RULES.readSlotsPage).toEqual({
    effect: 'read',
  })
})
it('不正limit/カーソルを補修せず拒否する', async () => {
  const q = await queue()
  for (const limit of [0, 101, 1.5, NaN])
    await expect(
      q.readSlotsPage({ game: 'g', d4: 'd' }, null, limit),
    ).rejects.toThrow()
  for (const cursor of [-1, 1.5, NaN])
    await expect(
      q.readSlotsPage({ game: 'g', d4: 'd' }, cursor, 1),
    ).rejects.toThrow()
})

import { IDBFactory, IDBDatabase, IDBObjectStore } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  FirstBallAttemptPersistence,
  FirstBallAttemptPersistenceError,
} from './firstBallAttemptPersistence'
const tenantId = '10000000-0000-4000-8000-000000000001'
const gameId = '10000000-0000-4000-8000-000000000002'
const d5 = '10000000-0000-4000-8000-000000000003'
const attempt = '10000000-0000-4000-8000-000000000004'
const other = '20000000-0000-4000-8000-000000000001'
let handles: FirstBallAttemptPersistence[]
function input() {
  return {
    tenantId,
    gameId,
    d5,
    events: [
      {
        game_id: gameId,
        d5,
        d1: 1,
        d4: 'opaque-generation',
        d2: 'opaque-time',
        payload: { course: { x: '132', y: '139' } },
      },
    ],
  }
}
async function open() {
  const handle = await FirstBallAttemptPersistence.open()
  handles.push(handle)
  return handle
}
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
  handles = []
})
afterEach(() => {
  handles.forEach((handle) => handle.close())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
describe('初球attempt耐久バリア', () => {
  it('再起動と再送で同じattemptと要求を復元する', async () => {
    const handle = await open(),
      saved = await handle.prepare(input(), attempt)
    handle.close()
    const reloaded = await open()
    expect(await reloaded.read(tenantId, gameId)).toEqual(saved)
    expect(await reloaded.prepare(input(), other)).toEqual(saved)
    expect(saved.attemptId).toBe(attempt)
  })
  it('キー順序だけ違う要求は同じattemptを再利用する', async () => {
    const handle = await open()
    const saved = await handle.prepare(input(), attempt)
    const value = input()
    value.events = [
      Object.fromEntries(
        Object.entries(value.events[0]!).reverse(),
      ) as (typeof value.events)[number],
    ]
    expect(await handle.prepare(value)).toEqual(saved)
  })
  it('破損した永続要求を補修せず拒否する', async () => {
    const handle = await open()
    const saved = await handle.prepare(input(), attempt)
    const database = await new Promise<globalThis.IDBDatabase>(
      (resolve, reject) => {
        const request = indexedDB.open('pitchlog-first-ball-attempt', 1)
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(new Error('fixture open failure'))
      },
    )
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = database.transaction('attempts', 'readwrite')
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(new Error('fixture write failure'))
        tx.objectStore('attempts').put({
          ...saved,
          requestJson: '[{"game_id":"wrong","d5":"wrong"}]',
        })
      })
      await expect(handle.read(tenantId, gameId)).rejects.toBeInstanceOf(
        FirstBallAttemptPersistenceError,
      )
      await expect(handle.prepare(input(), attempt)).rejects.toBeInstanceOf(
        FirstBallAttemptPersistenceError,
      )
    } finally {
      database.close()
    }
  })
  it('並行prepareは最初の耐久保存へ収束する', async () => {
    const a = await open(),
      b = await open()
    const results = await Promise.all([
      a.prepare(input(), attempt),
      b.prepare(input(), other),
    ])
    expect(results[0]).toEqual(results[1])
  })
  it('異内容・D5置換を拒否し、元要求は経過時間によらず保持する', async () => {
    const handle = await open(),
      saved = await handle.prepare(input(), attempt)
    const changed = input()
    changed.events[0]!.payload.course.x = '131'
    await expect(handle.prepare(changed)).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    const replaced = input()
    replaced.d5 = other
    replaced.events[0]!.d5 = other
    await expect(handle.prepare(replaced)).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    vi.spyOn(Date, 'now').mockReturnValue(
      Date.now() + 1000 * 60 * 60 * 24 * 365,
    )
    expect(await handle.read(tenantId, gameId)).toEqual(saved)
  })
  it.each([
    'recording_right_proof',
    'device_credential',
    'Cookie',
    'Authorization',
    'token',
  ])('資格キー%sを複製せず原値を例外へ出さない', async (key) => {
    const handle = await open(),
      value = input()
    Object.assign(value.events[0]!.payload, {
      [key]: 'private-material-marker',
    })
    let error: unknown
    try {
      await handle.prepare(value)
    } catch (caught) {
      error = caught
    }
    expect(error).toBeInstanceOf(FirstBallAttemptPersistenceError)
    expect(String(error)).not.toContain('private-material-marker')
    expect(error).not.toHaveProperty('cause')
    expect(await handle.read(tenantId, gameId)).toBeNull()
  })
  it.each([NaN, Infinity, undefined, -0])(
    'JSON補修値%sを拒否する',
    async (bad) => {
      const handle = await open(),
        value = input()
      Object.assign(value.events[0]!.payload, { invalid: bad })
      await expect(handle.prepare(value)).rejects.toBeInstanceOf(
        FirstBallAttemptPersistenceError,
      )
    },
  )
  it('getterを呼ばず拒否する', async () => {
    const handle = await open(),
      value = input(),
      getter = vi.fn(() => 1)
    Object.defineProperty(value.events[0]!.payload, 'getter', {
      get: getter,
      enumerable: true,
    })
    await expect(handle.prepare(value)).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    expect(getter).not.toHaveBeenCalled()
  })
  it('tenant分離と要求gameを照合する', async () => {
    const handle = await open()
    await handle.prepare(input(), attempt)
    expect(await handle.read(other, gameId)).toBeNull()
    const bad = input()
    bad.events[0]!.game_id = other
    await expect(handle.prepare(bad)).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
  })
  it('非正準UUID・非secure context・close後は拒否する', async () => {
    const handle = await open()
    await expect(
      handle.prepare({ ...input(), tenantId: 'bad' }),
    ).rejects.toBeInstanceOf(FirstBallAttemptPersistenceError)
    vi.stubGlobal('isSecureContext', false)
    await expect(handle.prepare(input())).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    vi.stubGlobal('isSecureContext', true)
    handle.close()
    await expect(handle.read(tenantId, gameId)).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
  })
  it('strict durability非対応と書込失敗で保存成功を返さない', async () => {
    const handle = await open(),
      original = IDBDatabase.prototype.transaction
    vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementation(function (
      this: IDBDatabase,
      names,
      mode,
    ) {
      return original.call(this, names, mode)
    })
    await expect(handle.prepare(input())).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    vi.restoreAllMocks()
    vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(() => {
      throw new Error('disk failure')
    })
    await expect(handle.prepare(input())).rejects.toBeInstanceOf(
      FirstBallAttemptPersistenceError,
    )
    vi.restoreAllMocks()
    expect(await handle.read(tenantId, gameId)).toBeNull()
  })
})

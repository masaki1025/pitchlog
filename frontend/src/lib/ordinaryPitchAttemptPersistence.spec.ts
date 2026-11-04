import { IDBDatabase, IDBFactory, IDBObjectStore } from 'fake-indexeddb'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import {
  OrdinaryPitchAttemptPersistence,
  OrdinaryAttemptPersistenceError,
} from './ordinaryPitchAttemptPersistence'
import { FirstBallAttemptPersistence } from './firstBallAttemptPersistence'
const tenantId = '11111111-1111-4111-8111-111111111111',
  gameId = '22222222-2222-4222-8222-222222222222',
  d5 = '33333333-3333-4333-8333-333333333333',
  attempt = '44444444-4444-4444-8444-444444444444',
  other = '55555555-5555-4555-8555-555555555555'
const handles: { close: () => void }[] = []
const input = (d1 = 1, key = d5) => ({
  tenantId,
  gameId,
  d4: 'opaque-D4',
  d1,
  d5: key,
  events: [
    {
      game_id: gameId,
      d4: 'opaque-D4',
      d1,
      d5: key,
      payload: { note: 'observation' },
      d2: d1,
    },
  ],
})
async function open() {
  const h = await OrdinaryPitchAttemptPersistence.open()
  handles.push(h)
  return h
}
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
})
afterEach(() => {
  handles.splice(0).forEach((h) => h.close())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('再起動で同じslot原要求/attemptを復元し、再送で再採番しない', async () => {
  const h = await open()
  const saved = await h.prepare(input(), attempt)
  h.close()
  const reloaded = await open()
  expect(await reloaded.read(input())).toEqual(saved)
  expect(await reloaded.prepare(input(), other)).toEqual(saved)
})
it('異内容・同slot新D5置換を原子的に拒否し旧要求を保持する', async () => {
  const h = await open(),
    saved = await h.prepare(input(), attempt)
  const changed = input()
  changed.events[0]!.payload.note = 'other'
  await expect(h.prepare(changed)).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  await expect(h.prepare(input(1, other))).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  expect(await h.read(input())).toEqual(saved)
  expect(await h.read(input(1, other))).toBeNull()
})
it('未終結slotがあっても次の独立slotを保存でき、attemptは混ぜない', async () => {
  const h = await open()
  const first = await h.prepare(input(), attempt)
  const second = await h.prepare(input(2, other))
  expect(second.attemptId).not.toBe(first.attemptId)
  expect(second.d1).toBe(2)
  expect(await h.read(input())).toEqual(first)
  expect(await h.read(input(2, other))).toEqual(second)
})
it('競合する同slot同内容は一つのattemptへ収束する', async () => {
  const a = await open(),
    b = await open()
  const records = await Promise.all([
    a.prepare(input(), attempt),
    b.prepare(input(), other),
  ])
  expect(records[0]).toEqual(records[1])
})
it('別tenant/game/D4とraw事件のslot移植を拒否する', async () => {
  const h = await open(),
    saved = await h.prepare(input(), attempt)
  for (const key of [
    { ...input(), tenantId: other },
    { ...input(), gameId: other },
    { ...input(), d4: 'other-generation' },
  ])
    expect(await h.read(key)).toBeNull()
  const bad = input()
  bad.events[0]!.d1 = 2
  await expect(h.prepare(bad)).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  expect(await h.read(input())).toEqual(saved)
})
it('旧初球storeを変更/上書きせず分離する', async () => {
  const first = await FirstBallAttemptPersistence.open()
  handles.push(first)
  const old = await first.prepare(input(), attempt)
  const h = await open()
  const current = await h.prepare(input(2, other))
  expect(await first.read(tenantId, gameId)).toEqual(old)
  expect(await h.read(input(2, other))).toEqual(current)
})
it.each([
  'device_credential',
  'Cookie',
  'Authorization',
  'recording_right_proof',
  'token',
])('資格%sを耐久eventsへ複製しない', async (key) => {
  const h = await open(),
    value = input()
  Object.assign(value.events[0]!.payload, { [key]: 'private-marker' })
  let error: unknown
  try {
    await h.prepare(value)
  } catch (caught) {
    error = caught
  }
  expect(error).toBeInstanceOf(OrdinaryAttemptPersistenceError)
  expect(String(error)).not.toContain('private-marker')
  expect(error).not.toHaveProperty('cause')
  expect(await h.read(input())).toBeNull()
})
it('strict非対応とadd故障は成功を返さず旧slotを保持する', async () => {
  const h = await open(),
    saved = await h.prepare(input(), attempt),
    original = IDBDatabase.prototype.transaction
  vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementation(function (
    this: IDBDatabase,
    names,
    mode,
  ) {
    return original.call(this, names, mode)
  })
  await expect(h.prepare(input(2, other))).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  vi.restoreAllMocks()
  vi.spyOn(IDBObjectStore.prototype, 'add').mockImplementation(() => {
    throw new Error('injected-write-failure')
  })
  await expect(h.prepare(input(2, other))).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  vi.restoreAllMocks()
  expect(await h.read(input())).toEqual(saved)
  expect(await h.read(input(2, other))).toBeNull()
})
it('secure/closeと不正D1/キーを閉拒否し期限で消去しない', async () => {
  const h = await open(),
    saved = await h.prepare(input(), attempt)
  for (const d1 of [0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])
    await expect(h.prepare({ ...input(), d1 })).rejects.toBeInstanceOf(
      OrdinaryAttemptPersistenceError,
    )
  vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 365 * 24 * 60 * 60 * 1000)
  expect(await h.read(input())).toEqual(saved)
  vi.stubGlobal('isSecureContext', false)
  await expect(h.read(input())).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
  vi.stubGlobal('isSecureContext', true)
  h.close()
  await expect(h.read(input())).rejects.toBeInstanceOf(
    OrdinaryAttemptPersistenceError,
  )
})

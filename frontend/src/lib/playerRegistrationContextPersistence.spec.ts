import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  PlayerRegistrationContextPersistence,
  isPlayerRegistrationContext,
  type PlayerRegistrationContext,
} from './playerRegistrationContextPersistence'

const tenant = '11111111-1111-4111-8111-111111111111'
const game = '22222222-2222-4222-8222-222222222222'
const away = '33333333-3333-4333-8333-333333333333'
const home = '44444444-4444-4444-8444-444444444444'
const stores: PlayerRegistrationContextPersistence[] = []
const databaseNames: string[] = []
let sequence = 0

const value: PlayerRegistrationContext = {
  tenantId: tenant,
  gameId: game,
  d4: 'grant-1',
  awayTeamId: away,
  homeTeamId: home,
}

async function store(
  name = `registration-context-${++sequence}`,
): Promise<PlayerRegistrationContextPersistence> {
  if (!databaseNames.includes(name)) databaseNames.push(name)
  const opened = await PlayerRegistrationContextPersistence.open(name)
  stores.push(opened)
  return opened
}

beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
})

afterEach(async () => {
  for (const opened of stores.splice(0)) opened.close()
  for (const name of databaseNames.splice(0)) {
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.deleteDatabase(name)
      request.onsuccess = () => resolve()
      request.onerror = () => reject(request.error)
      request.onblocked = () => reject(new Error('テスト DB を削除できません'))
    })
  }
  vi.unstubAllGlobals()
})

describe('playerRegistrationContextPersistence', () => {
  it('再起動後も同じ試合の登録文脈を返す', async () => {
    const name = `registration-context-${++sequence}`
    const first = await store(name)
    await first.save(value)
    first.close()
    stores.splice(stores.indexOf(first), 1)

    const reopened = await store(name)
    expect(await reopened.read(tenant, game)).toEqual(value)
  })

  it('別テナント・別試合の文脈を混ぜない', async () => {
    const opened = await store()
    await opened.save(value)
    expect(
      await opened.read('55555555-5555-4555-8555-555555555555', game),
    ).toBeUndefined()
    expect(
      await opened.read(tenant, '66666666-6666-4666-8666-666666666666'),
    ).toBeUndefined()
  })

  it('外形不正の文脈を保存しない', async () => {
    const opened = await store()
    await expect(
      opened.save({ ...value, awayTeamId: 'not-uuid' }),
    ).rejects.toThrow()
    expect(isPlayerRegistrationContext({ ...value, extra: true })).toBe(false)
  })
})

import 'fake-indexeddb/auto'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  TemporaryPlayerMappingConflictError,
  TemporaryPlayerMappingStore,
  type TemporaryPlayerMappingRecord,
} from './temporaryPlayerMappingStore'

const tenant = '11111111-1111-4111-8111-111111111111'
const game = '22222222-2222-4222-8222-222222222222'
const otherGame = '33333333-3333-4333-8333-333333333333'
const temporary = '44444444-4444-4444-8444-444444444444'
const official = '55555555-5555-4555-8555-555555555555'
const otherOfficial = '66666666-6666-4666-8666-666666666666'
const stores: TemporaryPlayerMappingStore[] = []
const databaseNames: string[] = []
let sequence = 0

function record(
  overrides: Partial<TemporaryPlayerMappingRecord> = {},
): TemporaryPlayerMappingRecord {
  return {
    temporaryId: temporary,
    officialId: official,
    tenantId: tenant,
    gameId: game,
    d4: 'grant-1',
    d5: '77777777-7777-4777-8777-777777777777',
    ...overrides,
  }
}

async function store(
  name = `mapping-store-${++sequence}`,
): Promise<TemporaryPlayerMappingStore> {
  if (!databaseNames.includes(name)) databaseNames.push(name)
  const opened = await TemporaryPlayerMappingStore.open(name)
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

describe('temporaryPlayerMappingStore', () => {
  it('再起動後も同じ一時IDを同じ正式IDへ解決する', async () => {
    const name = `mapping-store-${++sequence}`
    const first = await store(name)
    await first.append(record())
    first.close()
    stores.splice(stores.indexOf(first), 1)

    const reopened = await store(name)
    expect(await reopened.read(temporary)).toEqual(record())
  })

  it('同じ写像の再送を重複保存しない', async () => {
    const opened = await store()
    await opened.append(record())
    await opened.append(record())
    expect(await opened.readGame(tenant, game)).toHaveLength(1)
  })

  it('同じ一時IDを別の正式IDへ付け替えない', async () => {
    const opened = await store()
    await opened.append(record())
    await expect(
      opened.append(record({ officialId: otherOfficial })),
    ).rejects.toBeInstanceOf(TemporaryPlayerMappingConflictError)
    expect(await opened.read(temporary)).toEqual(record())
  })

  it('同じ一時IDを別の試合へ流用しない', async () => {
    const opened = await store()
    await opened.append(record())
    await expect(
      opened.append(record({ gameId: otherGame })),
    ).rejects.toBeInstanceOf(TemporaryPlayerMappingConflictError)
    expect(await opened.read(temporary)).toEqual(record())
  })

  it('試合ごとに写像を有限に読み出す', async () => {
    const opened = await store()
    await opened.append(record())
    await opened.append(
      record({
        temporaryId: '88888888-8888-4888-8888-888888888888',
        gameId: otherGame,
      }),
    )
    expect(await opened.readGame(tenant, game)).toEqual([record()])
  })

  it('外形不正の写像を保存しない', async () => {
    const opened = await store()
    await expect(
      opened.append(record({ temporaryId: 'not-uuid' })),
    ).rejects.toThrow()
    await expect(opened.read('not-uuid')).rejects.toThrow()
  })
})

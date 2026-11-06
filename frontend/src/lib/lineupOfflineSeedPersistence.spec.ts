import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { IDBFactory, IDBKeyRange } from 'fake-indexeddb'
import fixture from '../api/fixtures/lineupPrefixGame.v3.json'
import { isLineupPrefixGame } from '../api/lineupPrefixGame'
import { GameStartPersistence } from './gameStartPersistence'
import {
  readLineupOfflineSeed,
  saveLineupOfflineSeed,
} from './lineupOfflineSeedPersistence'

const seed = structuredClone(fixture.value)
if (!isLineupPrefixGame(seed) || seed.prefix_ref.length !== '0')
  throw new Error('fixture不正')
const tenant = seed.prefix_ref.tenantId
const grant = {
  tenant_id: tenant,
  game_id: seed.id,
  device_id: tenant,
  start_request_id: seed.prefix_ref.origin.eventId,
  d4: seed.current_d4,
  away_lineup_id: seed.lineups.away.lineup_id,
  home_lineup_id: seed.lineups.home.lineup_id,
  recovery_generation: seed.recovery_generation,
  recording_right_proof: 'unit-only-proof',
}
let activeGrant = { ...grant }
beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('IDBKeyRange', IDBKeyRange)
  vi.stubGlobal('isSecureContext', true)
  activeGrant = { ...grant }
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readDevice: async () => ({
      device_id: tenant,
      tenant_id: tenant,
      device_credential: 'unit-only',
    }),
    readStart: async () => ({ status: 'received', grant: activeGrant }),
    close: () => {},
  } as unknown as GameStartPersistence)
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
it('C2読取の0件seedをstrict commitし、同資格だけで再起動後に読める', async () => {
  await saveLineupOfflineSeed(seed, tenant)
  expect(await readLineupOfflineSeed(tenant, seed.id)).toEqual(seed)
  await saveLineupOfflineSeed(seed, tenant)
  expect(await readLineupOfflineSeed(tenant, seed.id)).toEqual(seed)
})
it('開始grant不在・D4変更・recovery変更・名簿変更を閉拒否する', async () => {
  await saveLineupOfflineSeed(seed, tenant)
  activeGrant = {
    ...grant,
    d4: 'd4.2.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
  }
  expect(await readLineupOfflineSeed(tenant, seed.id)).toBeNull()
  activeGrant = { ...grant, recovery_generation: '2' }
  await expect(readLineupOfflineSeed(tenant, seed.id)).rejects.toThrow()
  activeGrant = {
    ...grant,
    start_request_id: '99999999-9999-4999-8999-999999999999',
  }
  await expect(readLineupOfflineSeed(tenant, seed.id)).rejects.toThrow()
  activeGrant = {
    ...grant,
    away_lineup_id: '99999999-9999-4999-8999-999999999999',
  }
  await expect(readLineupOfflineSeed(tenant, seed.id)).rejects.toThrow()
})
it('保存行のsource refとartifact束縛の同時変更を成功へ補わない', async () => {
  await saveLineupOfflineSeed(seed, tenant)
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open('pitchlog-lineup-offline-seed-v1', 1)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  try {
    const key = [tenant, seed.id, seed.current_d4]
    const original = await new Promise<Record<string, unknown>>(
      (resolve, reject) => {
        const request = db
          .transaction('seeds', 'readonly')
          .objectStore('seeds')
          .get(key)
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error)
      },
    )
    for (const patch of [
      { artifactSha256: '0'.repeat(64) },
      { sourceRef: { ...seed.prefix_ref, length: '1' } },
    ]) {
      const tx = db.transaction('seeds', 'readwrite')
      tx.objectStore('seeds').put({ ...original, ...patch })
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject()
      })
      await expect(readLineupOfflineSeed(tenant, seed.id)).rejects.toThrow()
    }
  } finally {
    db.close()
  }
})

it('同時保存は同一取引で既行と照合し、別seedを後勝ち上書きしない', async () => {
  const alternate = { ...structuredClone(seed), plate_umpire: '別の真正読取値' }
  expect(isLineupPrefixGame(alternate)).toBe(true)
  const results = await Promise.allSettled([
    saveLineupOfflineSeed(seed, tenant),
    saveLineupOfflineSeed(alternate, tenant),
  ])
  expect(results.map((result) => result.status).sort()).toEqual([
    'fulfilled',
    'rejected',
  ])
  const stored = await readLineupOfflineSeed(tenant, seed.id)
  const winner = results[0]!.status === 'fulfilled' ? seed : alternate
  expect(stored).toEqual(winner)
  await expect(saveLineupOfflineSeed(winner, tenant)).resolves.toBeUndefined()
  expect(await readLineupOfflineSeed(tenant, seed.id)).toEqual(winner)
})

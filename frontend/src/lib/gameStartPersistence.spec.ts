import { IDBDatabase, IDBFactory, IDBObjectStore } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  GameStartPersistence,
  GameStartPersistenceError,
} from './gameStartPersistence'

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const requestId = '10000000-0000-4000-8000-000000000003'
const device = '10000000-0000-4000-8000-000000000004'
const other = '20000000-0000-4000-8000-000000000001'
const credential = 'public-test-device-credential'
const proof = 'public-test-recording-proof'
const owner = {
  tenant_id: tenant,
  game_id: game,
  start_request_id: requestId,
  device_id: device,
}
const enrolled = {
  tenant_id: tenant,
  device_id: device,
  device_credential: credential,
}
let handles: GameStartPersistence[] = []

function request(id = requestId) {
  const side = Array.from({ length: 9 }, (_, index) => ({
    player_id: `30000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    batting_order: index + 1,
    fielding_position: { selected: index + 1 },
  }))
  return {
    start_request_id: id,
    device_id: device,
    device_credential: credential,
    away: side,
    home: structuredClone(side),
  }
}
function grant() {
  return {
    ...owner,
    d4: 'opaque-reference',
    recovery_generation: '9223372036854775807',
    recording_right_proof: proof,
    started_at: '2026-10-26T12:34:56Z',
    away_lineup_id: other,
    home_lineup_id: game,
  }
}
async function open() {
  const handle = await GameStartPersistence.open()
  handles.push(handle)
  return handle
}
async function prepared() {
  const handle = await open()
  await handle.rememberDevice(enrolled, tenant)
  await handle.prepareStart(tenant, game, request())
  return handle
}
async function rawDatabase(): Promise<globalThis.IDBDatabase> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open('pitchlog-game-start', 1)
    opening.onsuccess = () => resolve(opening.result)
    opening.onerror = () => reject(new Error('fixture open failed'))
  })
}
async function rawPut(store: string, value: unknown) {
  const database = await rawDatabase()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(store, 'readwrite')
      transaction.oncomplete = () => resolve()
      transaction.onabort = () => reject(new Error('fixture put failed'))
      transaction.objectStore(store).put(value)
    })
  } finally {
    database.close()
  }
}
async function safeFailure(promise: Promise<unknown>) {
  let caught: unknown
  try {
    await promise
  } catch (error) {
    caught = error
  }
  expect(caught).toBeInstanceOf(GameStartPersistenceError)
  expect(String(caught)).toBe(
    'GameStartPersistenceError: 開始データを保存・復元できません',
  )
  expect(JSON.stringify(caught)).not.toContain(credential)
  expect(JSON.stringify(caught)).not.toContain(proof)
  expect(caught).not.toHaveProperty('cause')
}

beforeEach(() => {
  vi.stubGlobal('indexedDB', new IDBFactory())
  vi.stubGlobal('isSecureContext', true)
  handles = []
})
afterEach(() => {
  for (const handle of handles) handle.close()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('開始要求のIndexedDB保存境界', () => {
  it('secure contextまたはIDB不在では保存を開始しない', async () => {
    vi.stubGlobal('isSecureContext', false)
    await safeFailure(GameStartPersistence.open())
    vi.stubGlobal('isSecureContext', true)
    vi.stubGlobal('indexedDB', undefined)
    await safeFailure(GameStartPersistence.open())
  })
  it('原open例外に資格があっても元例外を保持しない', async () => {
    vi.spyOn(indexedDB, 'open').mockImplementation(() => {
      throw new Error(credential + proof)
    })
    await safeFailure(GameStartPersistence.open())
  })
  it('端末pairを保存/再openで復元し、同値だけ冪等にする', async () => {
    const first = await open()
    await first.rememberDevice(enrolled, tenant)
    await first.rememberDevice(enrolled, tenant)
    first.close()
    const restored = await open()
    expect(await restored.readDevice(tenant)).toEqual(enrolled)
    await safeFailure(
      restored.rememberDevice({ ...enrolled, device_id: other }, tenant),
    )
    await safeFailure(
      restored.rememberDevice(
        { ...enrolled, device_credential: 'different-public-value' },
        tenant,
      ),
    )
    expect(await restored.readDevice(tenant)).toEqual(enrolled)
    expect(await restored.readDevice(other)).toBeNull()
  })
  it('tenant不一致enrollを保存しない', async () => {
    const handle = await open()
    await safeFailure(handle.rememberDevice(enrolled, other))
    expect(await handle.readDevice(tenant)).toBeNull()
  })
  it('pair不在/別device/別資格を開始要求へ混ぜない', async () => {
    const handle = await open()
    await safeFailure(handle.prepareStart(tenant, game, request()))
    await handle.rememberDevice(enrolled, tenant)
    await safeFailure(
      handle.prepareStart(tenant, game, { ...request(), device_id: other }),
    )
    await safeFailure(
      handle.prepareStart(tenant, game, {
        ...request(),
        device_credential: 'different-public-value',
      }),
    )
    expect(await handle.readStart(tenant, game)).toBeNull()
  })
  it('入力後の変更を混入させず全payloadと同IDを再openで復元する', async () => {
    const handle = await open()
    await handle.rememberDevice(enrolled, tenant)
    const input = request()
    const before = structuredClone(input)
    const pending = handle.prepareStart(tenant, game, input)
    input.away[0]!.fielding_position.selected = 8
    const receipt = await pending
    expect(receipt.request).toEqual(before)
    expect(receipt.status).toBe('pending')
    expect(receipt.grant).toBeNull()
    handle.close()
    const restored = await open()
    expect((await restored.readStart(tenant, game))?.request).toEqual(before)
    expect(await restored.readStart(tenant, other)).toBeNull()
    expect(await restored.readStart(other, game)).toBeNull()
  })
  it('同ID別payloadと別IDへの未解決置換を拒否する', async () => {
    const handle = await prepared()
    const changed = request()
    changed.home[0]!.fielding_position.selected = 8
    await safeFailure(handle.prepareStart(tenant, game, changed))
    await safeFailure(handle.prepareStart(tenant, game, request(other)))
    expect((await handle.readStart(tenant, game))?.request).toEqual(request())
  })
  it('JSON objectのkey順序差だけでは別payloadにしない', async () => {
    const handle = await prepared()
    const input = request()
    const reversed = {
      home: input.home,
      away: input.away,
      device_credential: input.device_credential,
      device_id: input.device_id,
      start_request_id: input.start_request_id,
    }
    expect((await handle.prepareStart(tenant, game, reversed)).request).toEqual(
      request(),
    )
  })
  it('unknownは元要求を保持しreload後も新IDで置換しない', async () => {
    const handle = await prepared()
    await handle.markUnknown(owner)
    handle.close()
    const restored = await open()
    const saved = await restored.readStart(tenant, game)
    expect(saved?.status).toBe('unknown')
    expect(saved?.request).toEqual(request())
    expect(saved?.grant).toBeNull()
    expect((await restored.prepareStart(tenant, game, request())).status).toBe(
      'unknown',
    )
    await safeFailure(restored.prepareStart(tenant, game, request(other)))
  })
  it('別owner応答/期待要求なしのgrantを保存しない', async () => {
    const handle = await prepared()
    for (const field of [
      'tenant_id',
      'game_id',
      'start_request_id',
      'device_id',
    ] as const) {
      await safeFailure(
        handle.rememberGrant(owner, { ...grant(), [field]: other }),
      )
    }
    await safeFailure(
      handle.rememberGrant(
        { ...owner, game_id: other },
        { ...grant(), game_id: other },
      ),
    )
    expect((await handle.readStart(tenant, game))?.status).toBe('pending')
  })
  it('grantを不可分に保存し、遅延unknownで降格せず同応答だけ再保存する', async () => {
    const handle = await prepared()
    await handle.markUnknown(owner)
    const received = await handle.rememberGrant(owner, grant())
    expect(received.status).toBe('received')
    expect(received.grant).toEqual(grant())
    expect((await handle.markUnknown(owner)).status).toBe('received')
    expect(await handle.rememberGrant(owner, grant())).toEqual(received)
    await safeFailure(
      handle.rememberGrant(owner, {
        ...grant(),
        recording_right_proof: 'conflicting-public-proof',
      }),
    )
    handle.close()
    const restored = await open()
    expect(await restored.readStart(tenant, game)).toEqual(received)
    expect((await restored.prepareStart(tenant, game, request())).status).toBe(
      'received',
    )
  })
  it('同時2handleの異なる要求を同じgameへ上書きしない', async () => {
    const first = await open()
    const second = await open()
    await first.rememberDevice(enrolled, tenant)
    const results = await Promise.allSettled([
      first.prepareStart(tenant, game, request()),
      second.prepareStart(tenant, game, request(other)),
    ])
    expect(
      results.filter((result) => result.status === 'fulfilled'),
    ).toHaveLength(1)
    expect(
      results.filter((result) => result.status === 'rejected'),
    ).toHaveLength(1)
    const winner = results.find((result) => result.status === 'fulfilled')
    if (winner?.status !== 'fulfilled')
      throw new Error('fixture has no committed winner')
    expect(await second.readStart(tenant, game)).toEqual(winner.value)
  })
  it('request成功時点ではACKせずtransaction完了後だけ返す', async () => {
    const handle = await prepared()
    let acknowledged = false
    let checked = false
    const original = IDBObjectStore.prototype.put
    vi.spyOn(IDBObjectStore.prototype, 'put').mockImplementation(function (
      this: IDBObjectStore,
      ...args: Parameters<typeof original>
    ) {
      const result = original.apply(this, args)
      result.addEventListener('success', () => {
        checked = true
        expect(acknowledged).toBe(false)
      })
      return result
    })
    await handle.rememberGrant(owner, grant()).then(() => {
      acknowledged = true
    })
    expect(checked).toBe(true)
    expect(acknowledged).toBe(true)
  })
  it('grant put後abortならACKせず元pending/原要求を保持する', async () => {
    const handle = await prepared()
    const original = IDBObjectStore.prototype.put
    const spy = vi
      .spyOn(IDBObjectStore.prototype, 'put')
      .mockImplementation(function (
        this: IDBObjectStore,
        ...args: Parameters<typeof original>
      ) {
        const result = original.apply(this, args)
        this.transaction.abort()
        return result
      })
    await safeFailure(handle.rememberGrant(owner, grant()))
    spy.mockRestore()
    const previous = await handle.readStart(tenant, game)
    expect(previous?.status).toBe('pending')
    expect(previous?.grant).toBeNull()
    expect(previous?.request).toEqual(request())
    handle.close()
    expect((await (await open()).readStart(tenant, game))?.status).toBe(
      'pending',
    )
  })
  it('strict durabilityを要求し無視するstorageを成功扱いしない', async () => {
    const handle = await open()
    const original = IDBDatabase.prototype.transaction
    vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementation(function (
      this: IDBDatabase,
      storeNames,
      mode,
    ) {
      return original.call(this, storeNames, mode)
    })
    await safeFailure(handle.rememberDevice(enrolled, tenant))
  })
  it('破損行やpair不整合を自動修復せず拒否する', async () => {
    const handle = await prepared()
    await rawPut('starts', {
      owner,
      request: request(),
      status: 'received',
      grant: null,
    })
    await safeFailure(handle.readStart(tenant, game))
    await rawPut('starts', {
      owner,
      request: request(),
      status: 'pending',
      grant: null,
    })
    await rawPut('devices', {
      ...enrolled,
      device_credential: 'corrupt-public-value',
    })
    await safeFailure(handle.readStart(tenant, game))
  })
  it('閉じたhandle/後発insecure contextで保存を進めない', async () => {
    const handle = await prepared()
    handle.close()
    await safeFailure(handle.markUnknown(owner))
    const next = await open()
    vi.stubGlobal('isSecureContext', false)
    await safeFailure(next.rememberGrant(owner, grant()))
  })
})

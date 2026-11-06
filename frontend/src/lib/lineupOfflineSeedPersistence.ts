import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import {
  isLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { GameStartPersistence } from './gameStartPersistence'
import type { InitialGameStartResponse } from '../api/gameStart'

const DATABASE = 'pitchlog-lineup-offline-seed-v1'
const STORE = 'seeds'
const KEY_PATH = ['tenantId', 'gameId', 'd4'] as const

type Row = Readonly<{
  schemaVersion: 1
  tenantId: string
  gameId: string
  d4: string
  recoveryGeneration: string
  awayLineupId: string
  homeLineupId: string
  artifactSha256: string
  sourceRef: LineupPrefixGame['prefix_ref']
  seed: LineupPrefixGame
}>

function invalid(): never {
  throw new Error('開始後の断中入力seedを確認できません')
}

function isRow(
  value: unknown,
  grant: InitialGameStartResponse,
  tenant: string,
  game: string,
): value is Row {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return false
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'artifactSha256,awayLineupId,d4,gameId,homeLineupId,recoveryGeneration,schemaVersion,seed,sourceRef,tenantId' ||
    row.schemaVersion !== 1 ||
    row.tenantId !== tenant ||
    row.gameId !== game ||
    row.d4 !== grant.d4 ||
    row.recoveryGeneration !== grant.recovery_generation ||
    row.awayLineupId !== grant.away_lineup_id ||
    row.homeLineupId !== grant.home_lineup_id ||
    row.artifactSha256 !== artifactIdentity.sha256 ||
    !isLineupPrefixGame(row.seed)
  )
    return false
  const seed = row.seed
  return (
    seed.read_kind === 'lineup-prefix' &&
    seed.prefix_ref.length === '0' &&
    seed.next_position.d1 === '1' &&
    seed.prefix_ref.tenantId === tenant &&
    seed.prefix_ref.origin.kind === 'started-game' &&
    seed.prefix_ref.origin.eventId === grant.start_request_id &&
    seed.prefix_ref.checkpoint.id === grant.start_request_id &&
    seed.pa_start_source.kind === 'started-game' &&
    seed.pa_start_source.id === grant.start_request_id &&
    seed.id === game &&
    seed.current_d4 === grant.d4 &&
    seed.recovery_generation === grant.recovery_generation &&
    seed.lineups.away.lineup_id === grant.away_lineup_id &&
    seed.lineups.home.lineup_id === grant.home_lineup_id &&
    sameOrdinaryWire(row.sourceRef, seed.prefix_ref)
  )
}

/** 開始ACKの保存済み資格と、先にC2実GETで得た0件sourceだけを結ぶ。 */
async function grantFor(
  tenant: string,
  game: string,
): Promise<InitialGameStartResponse> {
  const store = await GameStartPersistence.open()
  try {
    const start = await store.readStart(tenant, game)
    const device = await store.readDevice(tenant)
    if (
      start?.status !== 'received' ||
      !start.grant ||
      !device ||
      device.device_id !== start.grant.device_id
    )
      invalid()
    return start.grant
  } finally {
    store.close()
  }
}

class SeedStore {
  readonly #db: IDBDatabase
  #closed = false
  private constructor(db: IDBDatabase) {
    this.#db = db
    db.onversionchange = () => this.close()
  }
  static async open(): Promise<SeedStore> {
    if (!globalThis.isSecureContext || typeof indexedDB?.open !== 'function')
      invalid()
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open(DATABASE, 1)
      request.onupgradeneeded = () => {
        try {
          request.result.createObjectStore(STORE, { keyPath: [...KEY_PATH] })
        } catch {
          request.transaction?.abort()
        }
      }
      request.onblocked = () =>
        reject(new Error('断中入力seedの保存領域を開けません'))
      request.onerror = () =>
        reject(new Error('断中入力seedの保存領域を開けません'))
      request.onsuccess = () => resolve(request.result)
    })
    try {
      if ([...db.objectStoreNames].sort().join(',') !== STORE) invalid()
      const keyPath = db
        .transaction(STORE, 'readonly')
        .objectStore(STORE).keyPath
      if (JSON.stringify(keyPath) !== JSON.stringify(KEY_PATH)) invalid()
      return new SeedStore(db)
    } catch (error) {
      db.close()
      throw error
    }
  }
  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#db.close()
  }
  async read(
    grant: InitialGameStartResponse,
    tenant: string,
    game: string,
  ): Promise<Row | null> {
    if (this.#closed) invalid()
    const key = [tenant, game, grant.d4]
    return new Promise<Row | null>((resolve, reject) => {
      const tx = this.#db.transaction(STORE, 'readonly')
      const request = tx.objectStore(STORE).get(key)
      request.onsuccess = () => {
        if (request.result === undefined) resolve(null)
        else if (isRow(request.result, grant, tenant, game))
          resolve(request.result)
        else reject(new Error('断中入力seedが不正です'))
      }
      request.onerror = () => reject(new Error('断中入力seedを読めません'))
      tx.onabort = () => reject(new Error('断中入力seedを読めません'))
    })
  }
  async write(row: Row, grant: InitialGameStartResponse): Promise<void> {
    if (this.#closed || !isRow(row, grant, row.tenantId, row.gameId)) invalid()
    await new Promise<void>((resolve, reject) => {
      let tx: IDBTransaction
      try {
        tx = this.#db.transaction(STORE, 'readwrite', { durability: 'strict' })
        if (tx.durability !== 'strict') {
          tx.abort()
          invalid()
        }
      } catch {
        reject(new Error('断中入力seedを厳密保存できません'))
        return
      }
      tx.oncomplete = () => resolve()
      tx.onabort = () => reject(new Error('断中入力seedを確定できません'))
      tx.onerror = () => {
        /* abortを終結とする。 */
      }
      const store = tx.objectStore(STORE)
      // 同storeのreadwrite取引を直列化し、別タブの未観測行を上書きしない。
      const request = store.get([row.tenantId, row.gameId, row.d4])
      request.onsuccess = () => {
        const previous: unknown = request.result
        if (previous === undefined) {
          store.add(row)
        } else if (
          !isRow(previous, grant, row.tenantId, row.gameId) ||
          !sameOrdinaryWire(previous, row)
        ) {
          tx.abort()
        }
      }
      request.onerror = () => tx.abort()
    })
  }
}

/** C2成功で検証された初期readのみをstrict確定し、完了まで画面をreadyにしない。 */
export async function saveLineupOfflineSeed(
  value: LineupPrefixGame,
  tenant: string,
): Promise<void> {
  const grant = await grantFor(tenant, value.id)
  const row: Row = structuredClone({
    schemaVersion: 1,
    tenantId: tenant,
    gameId: value.id,
    d4: grant.d4,
    recoveryGeneration: grant.recovery_generation,
    awayLineupId: grant.away_lineup_id,
    homeLineupId: grant.home_lineup_id,
    artifactSha256: artifactIdentity.sha256,
    sourceRef: value.prefix_ref,
    seed: value,
  })
  if (!isRow(row, grant, tenant, value.id)) invalid()
  const store = await SeedStore.open()
  try {
    await store.write(row, grant)
  } finally {
    store.close()
  }
}

/** 通信結果不明のGETだけが使う。最新server headの代用とは宣言しない。 */
export async function readLineupOfflineSeed(
  tenant: string,
  game: string,
): Promise<LineupPrefixGame | null> {
  const grant = await grantFor(tenant, game)
  const store = await SeedStore.open()
  try {
    const row = await store.read(grant, tenant, game)
    return row === null ? null : structuredClone(row.seed)
  } finally {
    store.close()
  }
}

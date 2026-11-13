/**
 * 一時選手 ID → 正式選手 ID の端末側の確定写像（docs/design/sync-protocol.md 4-4）。
 *
 * 写像は ACK の A4 を受け取ったときに一度だけ追記し、同じ一時 ID を別の正式 ID
 * へ付け替えない（C3）。キューとは別の IndexedDB に置き、再読み込み・再起動でも
 * 同じ写像を返す。選手行の作成やサーバー側の写像は適用核が所有する。
 */
const DATABASE = 'pitchlog-temporary-player-mappings'
const STORE = 'mappings'
const INDEX = 'by-game'

export type TemporaryPlayerMappingRecord = Readonly<{
  temporaryId: string
  officialId: string
  tenantId: string
  gameId: string
  d4: string
  d5: string
}>

const RECORD_KEYS = [
  'temporaryId',
  'officialId',
  'tenantId',
  'gameId',
  'd4',
  'd5',
] as const

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export class TemporaryPlayerMappingError extends Error {
  constructor(message = '一時選手 ID の写像を保存・復元できません') {
    super(message)
    this.name = 'TemporaryPlayerMappingError'
  }
}

export class TemporaryPlayerMappingConflictError extends TemporaryPlayerMappingError {
  constructor() {
    super('同じ一時選手 ID に別の正式選手 ID を割り当てられません')
    this.name = 'TemporaryPlayerMappingConflictError'
  }
}

function isRecord(value: unknown): value is TemporaryPlayerMappingRecord {
  if (
    value === null ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    (Object.getPrototypeOf(value) !== Object.prototype &&
      Object.getPrototypeOf(value) !== null)
  )
    return false
  const row = value as Record<string, unknown>
  return (
    Object.keys(row).length === RECORD_KEYS.length &&
    RECORD_KEYS.every((key) => Object.hasOwn(row, key)) &&
    [row.temporaryId, row.officialId, row.tenantId, row.gameId, row.d5].every(
      (item) => typeof item === 'string' && UUID_PATTERN.test(item),
    ) &&
    typeof row.d4 === 'string' &&
    row.d4.length > 0
  )
}

function sameRecord(
  first: TemporaryPlayerMappingRecord,
  second: TemporaryPlayerMappingRecord,
): boolean {
  return RECORD_KEYS.every((key) => Object.is(first[key], second[key]))
}

function secure(): void {
  if (
    globalThis.isSecureContext !== true ||
    typeof globalThis.indexedDB?.open !== 'function'
  )
    throw new TemporaryPlayerMappingError()
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () =>
      reject(request.error ?? new TemporaryPlayerMappingError())
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () =>
      reject(transaction.error ?? new TemporaryPlayerMappingError())
    transaction.onabort = () =>
      reject(transaction.error ?? new TemporaryPlayerMappingError())
  })
}

export class TemporaryPlayerMappingStore {
  #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(
    databaseName: string = DATABASE,
  ): Promise<TemporaryPlayerMappingStore> {
    try {
      secure()
      return await new Promise<TemporaryPlayerMappingStore>(
        (resolve, reject) => {
          const opening = indexedDB.open(databaseName, 1)
          let settled = false
          const fail = () => {
            settled = true
            reject(new TemporaryPlayerMappingError())
          }
          opening.onblocked = fail
          opening.onerror = (event) => {
            event.preventDefault()
            fail()
          }
          opening.onupgradeneeded = () => {
            try {
              const store = opening.result.createObjectStore(STORE, {
                keyPath: 'temporaryId',
              })
              store.createIndex(INDEX, ['tenantId', 'gameId'])
            } catch {
              try {
                opening.transaction?.abort()
              } catch {
                /* 終結済みでも成功へ戻さない。 */
              }
              fail()
            }
          }
          opening.onsuccess = () => {
            const database = opening.result
            if (settled) {
              database.close()
              return
            }
            try {
              if ([...database.objectStoreNames].join(',') !== STORE)
                throw new TemporaryPlayerMappingError()
              const store = database
                .transaction(STORE, 'readonly')
                .objectStore(STORE)
              if (
                JSON.stringify(store.keyPath) !==
                  JSON.stringify('temporaryId') ||
                [...store.indexNames].join(',') !== INDEX ||
                JSON.stringify(store.index(INDEX).keyPath) !==
                  JSON.stringify(['tenantId', 'gameId'])
              )
                throw new TemporaryPlayerMappingError()
              settled = true
              resolve(new TemporaryPlayerMappingStore(database))
            } catch {
              database.close()
              fail()
            }
          }
        },
      )
    } catch {
      throw new TemporaryPlayerMappingError()
    }
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#database.close()
  }

  /** 同じ一時 ID の再送は同じ写像だけを許し、別の正式 ID への付け替えを拒む。 */
  async append(
    record: TemporaryPlayerMappingRecord,
  ): Promise<TemporaryPlayerMappingRecord> {
    if (!isRecord(record)) throw new TemporaryPlayerMappingError()
    if (this.#closed) throw new TemporaryPlayerMappingError()
    const transaction = this.#database.transaction(STORE, 'readwrite')
    const done = transactionDone(transaction)
    try {
      const store = transaction.objectStore(STORE)
      const existing = await requestResult(store.get(record.temporaryId))
      if (existing !== undefined) {
        if (!isRecord(existing) || !sameRecord(existing, record)) {
          throw new TemporaryPlayerMappingConflictError()
        }
        await done
        return existing
      }
      store.put(record)
      await done
      return record
    } catch (error) {
      try {
        transaction.abort()
      } catch {
        /* 終結済みでも例外を成功へ変えない。 */
      }
      try {
        await done
      } catch {
        /* 元の失敗を返す。 */
      }
      throw error instanceof TemporaryPlayerMappingError
        ? error
        : new TemporaryPlayerMappingError()
    }
  }

  async read(
    temporaryId: string,
  ): Promise<TemporaryPlayerMappingRecord | undefined> {
    if (!UUID_PATTERN.test(temporaryId) || this.#closed)
      throw new TemporaryPlayerMappingError()
    const transaction = this.#database.transaction(STORE, 'readonly')
    const value = await requestResult(
      transaction.objectStore(STORE).get(temporaryId),
    )
    await transactionDone(transaction)
    if (value === undefined) return undefined
    if (!isRecord(value)) throw new TemporaryPlayerMappingError()
    return value
  }

  async readGame(
    tenantId: string,
    gameId: string,
  ): Promise<readonly TemporaryPlayerMappingRecord[]> {
    if (
      !UUID_PATTERN.test(tenantId) ||
      !UUID_PATTERN.test(gameId) ||
      this.#closed
    )
      throw new TemporaryPlayerMappingError()
    const transaction = this.#database.transaction(STORE, 'readonly')
    const values = await requestResult(
      transaction.objectStore(STORE).index(INDEX).getAll([tenantId, gameId]),
    )
    await transactionDone(transaction)
    if (!Array.isArray(values) || !values.every(isRecord))
      throw new TemporaryPlayerMappingError()
    return Object.freeze(values)
  }
}

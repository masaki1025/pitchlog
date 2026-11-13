/**
 * 断中のその場登録に必要な最小文脈（テナント・試合・記録権世代・両チーム）を
 * 端末へ固定する。試合の状態や記録権の証明ではなく、オンラインで検証済みの
 * 文脈を再起動後にも同じ値で使うための保存に限る。
 *
 * 保存値は GET/開始資格から得た識別子だけで、サーバーの再認可を代替しない。
 */
const DATABASE = 'pitchlog-player-registration-context'
const STORE = 'contexts'

export type PlayerRegistrationContext = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  awayTeamId: string
  homeTeamId: string
}>

const KEYS = ['tenantId', 'gameId', 'd4', 'awayTeamId', 'homeTeamId'] as const
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export class PlayerRegistrationContextError extends Error {
  constructor() {
    super('その場登録の端末文脈を保存・復元できません')
    this.name = 'PlayerRegistrationContextError'
  }
}

export function isPlayerRegistrationContext(
  value: unknown,
): value is PlayerRegistrationContext {
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
    Object.keys(row).length === KEYS.length &&
    KEYS.every((key) => Object.hasOwn(row, key)) &&
    [row.tenantId, row.gameId, row.awayTeamId, row.homeTeamId].every(
      (item) => typeof item === 'string' && UUID_PATTERN.test(item),
    ) &&
    typeof row.d4 === 'string' &&
    row.d4.length > 0
  )
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () =>
      reject(request.error ?? new PlayerRegistrationContextError())
  })
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () =>
      reject(transaction.error ?? new PlayerRegistrationContextError())
    transaction.onabort = () =>
      reject(transaction.error ?? new PlayerRegistrationContextError())
  })
}

export class PlayerRegistrationContextPersistence {
  #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(
    databaseName: string = DATABASE,
  ): Promise<PlayerRegistrationContextPersistence> {
    if (
      globalThis.isSecureContext !== true ||
      typeof globalThis.indexedDB?.open !== 'function'
    )
      throw new PlayerRegistrationContextError()
    try {
      return await new Promise<PlayerRegistrationContextPersistence>(
        (resolve, reject) => {
          const opening = indexedDB.open(databaseName, 1)
          let settled = false
          const fail = () => {
            settled = true
            reject(new PlayerRegistrationContextError())
          }
          opening.onblocked = fail
          opening.onerror = (event) => {
            event.preventDefault()
            fail()
          }
          opening.onupgradeneeded = () => {
            try {
              opening.result.createObjectStore(STORE, {
                keyPath: ['tenantId', 'gameId'],
              })
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
                throw new PlayerRegistrationContextError()
              const store = database
                .transaction(STORE, 'readonly')
                .objectStore(STORE)
              if (
                JSON.stringify(store.keyPath) !==
                JSON.stringify(['tenantId', 'gameId'])
              )
                throw new PlayerRegistrationContextError()
              settled = true
              resolve(new PlayerRegistrationContextPersistence(database))
            } catch {
              database.close()
              fail()
            }
          }
        },
      )
    } catch {
      throw new PlayerRegistrationContextError()
    }
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#database.close()
  }

  async save(context: PlayerRegistrationContext): Promise<void> {
    if (!isPlayerRegistrationContext(context) || this.#closed)
      throw new PlayerRegistrationContextError()
    const transaction = this.#database.transaction(STORE, 'readwrite')
    const done = transactionDone(transaction)
    try {
      transaction.objectStore(STORE).put(context)
      await done
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
      throw error instanceof PlayerRegistrationContextError
        ? error
        : new PlayerRegistrationContextError()
    }
  }

  async read(
    tenantId: string,
    gameId: string,
  ): Promise<PlayerRegistrationContext | undefined> {
    if (
      !UUID_PATTERN.test(tenantId) ||
      !UUID_PATTERN.test(gameId) ||
      this.#closed
    )
      throw new PlayerRegistrationContextError()
    const transaction = this.#database.transaction(STORE, 'readonly')
    const value = await requestResult(
      transaction.objectStore(STORE).get([tenantId, gameId]),
    )
    await transactionDone(transaction)
    if (value === undefined) return undefined
    if (!isPlayerRegistrationContext(value))
      throw new PlayerRegistrationContextError()
    if (value.tenantId !== tenantId || value.gameId !== gameId)
      throw new PlayerRegistrationContextError()
    return value
  }
}

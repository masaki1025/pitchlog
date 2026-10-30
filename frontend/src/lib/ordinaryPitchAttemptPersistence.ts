import { canonicalUuid } from '../api/authIntent'
import { canonicalAttemptEvents } from './firstBallAttemptPersistence'

const DATABASE = 'pitchlog-ordinary-pitch-attempt'
const STORE = 'attempts'
const INDEX = 'by-slot'
const KEY = ['tenantId', 'gameId', 'd4', 'd1', 'd5']
const SLOT_KEY = ['tenantId', 'gameId', 'd4', 'd1']
export type OrdinaryAttemptKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d1: number
  d5: string
}>
export type OrdinaryAttemptInput = OrdinaryAttemptKey &
  Readonly<{ events: readonly unknown[] }>
export type StoredOrdinaryAttempt = OrdinaryAttemptKey &
  Readonly<{ attemptId: string; requestJson: string }>
/** 原要求/資格/DOMエラーを外へ持ち出さない。 */
export class OrdinaryAttemptPersistenceError extends Error {
  constructor() {
    super('通常投球の送信準備を保存・復元できません')
    this.name = 'OrdinaryAttemptPersistenceError'
  }
}
function invalid(): never {
  throw new OrdinaryAttemptPersistenceError()
}
function validKey(key: OrdinaryAttemptKey): void {
  if (
    !key ||
    ![key.tenantId, key.gameId, key.d5].every(
      (v) => typeof v === 'string' && v.length === 36 && canonicalUuid.test(v),
    ) ||
    typeof key.d4 !== 'string' ||
    Array.from(key.d4).length < 1 ||
    Array.from(key.d4).length > 128 ||
    !Number.isSafeInteger(key.d1) ||
    key.d1 < 1
  )
    invalid()
}
function secure(): void {
  if (!globalThis.isSecureContext || !globalThis.indexedDB) invalid()
}
function readStored(
  value: unknown,
  key: OrdinaryAttemptKey,
): StoredOrdinaryAttempt {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    return invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'attemptId,d1,d4,d5,gameId,requestJson,tenantId' ||
    !KEY.every((k) => row[k] === key[k as keyof OrdinaryAttemptKey]) ||
    typeof row.attemptId !== 'string' ||
    row.attemptId.length !== 36 ||
    !canonicalUuid.test(row.attemptId) ||
    typeof row.requestJson !== 'string'
  )
    return invalid()
  const parsed: unknown = JSON.parse(row.requestJson)
  if (
    !Array.isArray(parsed) ||
    parsed.length !== 1 ||
    canonicalAttemptEvents(parsed) !== row.requestJson
  )
    return invalid()
  const event = parsed[0] as Record<string, unknown>
  if (
    !event ||
    event.game_id !== key.gameId ||
    event.d4 !== key.d4 ||
    event.d1 !== key.d1 ||
    event.d5 !== key.d5
  )
    return invalid()
  return Object.freeze({
    tenantId: key.tenantId,
    gameId: key.gameId,
    d4: key.d4,
    d1: key.d1,
    d5: key.d5,
    attemptId: row.attemptId,
    requestJson: row.requestJson,
  })
}
/** 未送信slotごとに固定する耐久attempt。次の独立slotを同じ要求へ統合しない。 */
export class OrdinaryPitchAttemptPersistence {
  #database: IDBDatabase
  #closed = false
  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }
  static async open(): Promise<OrdinaryPitchAttemptPersistence> {
    try {
      secure()
      return await new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE, 1)
        let failed = false
        const fail = () => {
          failed = true
          reject(new OrdinaryAttemptPersistenceError())
        }
        request.onerror = fail
        request.onblocked = fail
        request.onupgradeneeded = () => {
          try {
            const store = request.result.createObjectStore(STORE, {
              keyPath: KEY,
            })
            store.createIndex(INDEX, SLOT_KEY, { unique: true })
          } catch {
            request.transaction?.abort()
            fail()
          }
        }
        request.onsuccess = () => {
          const db = request.result
          if (failed) {
            db.close()
            return
          }
          try {
            if ([...db.objectStoreNames].join(',') !== STORE) return invalid()
            const store = db.transaction(STORE, 'readonly').objectStore(STORE)
            const index = store.index(INDEX)
            if (
              JSON.stringify(store.keyPath) !== JSON.stringify(KEY) ||
              [...store.indexNames].join(',') !== INDEX ||
              JSON.stringify(index.keyPath) !== JSON.stringify(SLOT_KEY) ||
              !index.unique
            )
              return invalid()
            resolve(new OrdinaryPitchAttemptPersistence(db))
          } catch {
            db.close()
            fail()
          }
        }
      })
    } catch {
      return invalid()
    }
  }
  close(): void {
    this.#closed = true
    this.#database.close()
  }
  #transaction(
    key: OrdinaryAttemptKey,
    expected?: StoredOrdinaryAttempt,
  ): Promise<StoredOrdinaryAttempt | null> {
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction
      try {
        secure()
        validKey(key)
        if (this.#closed) return invalid()
        tx = this.#database.transaction(
          STORE,
          expected ? 'readwrite' : 'readonly',
          expected ? { durability: 'strict' } : undefined,
        )
        if (expected && tx.durability !== 'strict') {
          tx.abort()
          return invalid()
        }
      } catch {
        reject(new OrdinaryAttemptPersistenceError())
        return
      }
      let result: StoredOrdinaryAttempt | null = null,
        ready = false
      const fail = () => {
        try {
          tx.abort()
        } catch {
          reject(new OrdinaryAttemptPersistenceError())
        }
      }
      tx.onerror = (event) => {
        event.preventDefault()
        fail()
      }
      tx.onabort = () => reject(new OrdinaryAttemptPersistenceError())
      tx.oncomplete = () =>
        ready ? resolve(result) : reject(new OrdinaryAttemptPersistenceError())
      try {
        const store = tx.objectStore(STORE)
        const request = store.get([
          key.tenantId,
          key.gameId,
          key.d4,
          key.d1,
          key.d5,
        ])
        request.onsuccess = () => {
          try {
            if (request.result !== undefined) {
              result = readStored(request.result, key)
              if (expected && result.requestJson !== expected.requestJson)
                return invalid()
            } else if (expected) {
              store.add(expected)
              result = expected
            }
            ready = true
          } catch {
            fail()
          }
        }
      } catch {
        fail()
      }
    })
  }
  async read(key: OrdinaryAttemptKey): Promise<StoredOrdinaryAttempt | null> {
    return this.#transaction(key)
  }
  async prepare(
    input: OrdinaryAttemptInput,
    attemptId?: string,
  ): Promise<StoredOrdinaryAttempt> {
    try {
      validKey(input)
      const key: OrdinaryAttemptKey = {
        tenantId: input.tenantId,
        gameId: input.gameId,
        d4: input.d4,
        d1: input.d1,
        d5: input.d5,
      }
      const expected = readStored(
        {
          ...key,
          attemptId: attemptId ?? crypto.randomUUID(),
          requestJson: canonicalAttemptEvents(input.events),
        },
        key,
      )
      const result = await this.#transaction(key, expected)
      if (!result) return invalid()
      return result
    } catch {
      return invalid()
    }
  }
}

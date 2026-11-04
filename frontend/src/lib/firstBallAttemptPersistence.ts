import { canonicalUuid } from '../api/authIntent'

const DATABASE = 'pitchlog-first-ball-attempt'
const STORE = 'attempts'

export type FirstBallAttemptInput = Readonly<{
  tenantId: string
  gameId: string
  d5: string
  events: readonly unknown[]
}>
export type StoredFirstBallAttempt = Readonly<{
  tenantId: string
  gameId: string
  d5: string
  attemptId: string
  /** 資格を含まない events の正準 JSON。同一要求の再送用。 */
  requestJson: string
}>

/** 原要求・資格・DOM例外を外へ保持しない。 */
export class FirstBallAttemptPersistenceError extends Error {
  constructor() {
    super('初球の送信準備を保存・復元できません')
    this.name = 'FirstBallAttemptPersistenceError'
  }
}
function invalid(): never {
  throw new FirstBallAttemptPersistenceError()
}
function uuid(value: unknown): string {
  if (typeof value !== 'string' || !canonicalUuid.test(value)) return invalid()
  return value
}
function secure(): void {
  if (!globalThis.isSecureContext || !globalThis.indexedDB) invalid()
}

/** JSON の補修（NaN/undefined/getter等）と資格の複製を拒む。 */
function canonical(value: unknown, ancestors: Set<object> = new Set()): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string')
    return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || Object.is(value, -0)) return invalid()
    return JSON.stringify(value)
  }
  if (typeof value !== 'object' || ancestors.has(value)) return invalid()
  if (Object.getOwnPropertySymbols(value).length !== 0) return invalid()
  ancestors.add(value)
  try {
    if (Array.isArray(value)) {
      if (Object.keys(value).length !== value.length) return invalid()
      const values: string[] = []
      for (let i = 0; i < value.length; i++) {
        const descriptor = Object.getOwnPropertyDescriptor(value, String(i))
        if (!descriptor || !('value' in descriptor)) return invalid()
        values.push(canonical(descriptor.value, ancestors))
      }
      return '[' + values.join(',') + ']'
    }
    const prototype = Object.getPrototypeOf(value)
    if (prototype !== Object.prototype && prototype !== null) return invalid()
    const fields: string[] = []
    for (const name of Object.getOwnPropertyNames(value).sort()) {
      if (
        /credential|cookie|password|authorization|recording.?right.?proof|secret|token/i.test(
          name,
        )
      )
        return invalid()
      const descriptor = Object.getOwnPropertyDescriptor(value, name)
      if (!descriptor?.enumerable || !('value' in descriptor)) return invalid()
      fields.push(
        JSON.stringify(name) + ':' + canonical(descriptor.value, ancestors),
      )
    }
    return '{' + fields.join(',') + '}'
  } finally {
    ancestors.delete(value)
  }
}
function readStored(
  value: unknown,
  tenant: string,
  game: string,
): StoredFirstBallAttempt {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    return invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
    'attemptId,d5,gameId,requestJson,tenantId'
  )
    return invalid()
  if (uuid(row.tenantId) !== tenant || uuid(row.gameId) !== game)
    return invalid()
  const attemptId = uuid(row.attemptId)
  const d5 = uuid(row.d5)
  if (typeof row.requestJson !== 'string') return invalid()
  const parsed: unknown = JSON.parse(row.requestJson)
  if (
    !Array.isArray(parsed) ||
    parsed.length !== 1 ||
    canonical(parsed) !== row.requestJson
  )
    return invalid()
  const event = parsed[0] as Record<string, unknown>
  if (!event || event.d5 !== d5 || event.game_id !== game) return invalid()
  return Object.freeze({
    tenantId: tenant,
    gameId: game,
    d5,
    attemptId,
    requestJson: row.requestJson,
  })
}

/** 初球1要求専用の耐久バリア。未確定要求を期限や再起動で破棄しない。 */
export class FirstBallAttemptPersistence {
  #database: IDBDatabase
  #closed = false
  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }
  static async open(): Promise<FirstBallAttemptPersistence> {
    try {
      secure()
      return await new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE, 1)
        let failed = false
        const fail = () => {
          failed = true
          reject(new FirstBallAttemptPersistenceError())
        }
        request.onerror = fail
        request.onblocked = fail
        request.onupgradeneeded = () => {
          try {
            request.result.createObjectStore(STORE, {
              keyPath: ['tenantId', 'gameId'],
            })
          } catch {
            request.transaction?.abort()
            fail()
          }
        }
        request.onsuccess = () => {
          const database = request.result
          if (failed) {
            database.close()
            return
          }
          try {
            if ([...database.objectStoreNames].join(',') !== STORE)
              return invalid()
            const tx = database.transaction(STORE, 'readonly')
            if (
              JSON.stringify(tx.objectStore(STORE).keyPath) !==
              '["tenantId","gameId"]'
            )
              return invalid()
            resolve(new FirstBallAttemptPersistence(database))
          } catch {
            database.close()
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
    tenant: string,
    game: string,
    expected?: StoredFirstBallAttempt,
  ): Promise<StoredFirstBallAttempt | null> {
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction
      try {
        secure()
        uuid(tenant)
        uuid(game)
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
        reject(new FirstBallAttemptPersistenceError())
        return
      }
      let result: StoredFirstBallAttempt | null = null
      let ready = false
      const fail = () => {
        try {
          tx.abort()
        } catch {
          reject(new FirstBallAttemptPersistenceError())
        }
      }
      tx.onerror = (event) => {
        event.preventDefault()
        fail()
      }
      tx.onabort = () => reject(new FirstBallAttemptPersistenceError())
      tx.oncomplete = () =>
        ready ? resolve(result) : reject(new FirstBallAttemptPersistenceError())
      try {
        const store = tx.objectStore(STORE)
        const request = store.get([tenant, game])
        request.onsuccess = () => {
          try {
            if (request.result !== undefined) {
              result = readStored(request.result, tenant, game)
              if (
                expected &&
                (result.d5 !== expected.d5 ||
                  result.requestJson !== expected.requestJson)
              )
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
  async read(
    tenantId: string,
    gameId: string,
  ): Promise<StoredFirstBallAttempt | null> {
    return this.#transaction(tenantId, gameId)
  }
  async prepare(
    input: FirstBallAttemptInput,
    attemptId?: string,
  ): Promise<StoredFirstBallAttempt> {
    try {
      const tenantId = uuid(input.tenantId)
      const gameId = uuid(input.gameId)
      const d5 = uuid(input.d5)
      if (!Array.isArray(input.events) || input.events.length !== 1)
        return invalid()
      const requestJson = canonical(input.events)
      const record = readStored(
        {
          tenantId,
          gameId,
          d5,
          requestJson,
          attemptId: uuid(attemptId ?? crypto.randomUUID()),
        },
        tenantId,
        gameId,
      )
      const result = await this.#transaction(tenantId, gameId, record)
      if (!result) return invalid()
      return result
    } catch {
      return invalid()
    }
  }
}

/** 新しいslot単位storeでも同じ非資格eventsの正準化を使う。旧storeは変更しない。 */
export function canonicalAttemptEvents(events: readonly unknown[]): string {
  if (!Array.isArray(events) || events.length !== 1) return invalid()
  return canonical(events)
}

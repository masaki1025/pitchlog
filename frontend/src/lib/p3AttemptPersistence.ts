/** D1なしP3の送信前原文を一試合一件だけ耐久化する。 */
import { canonicalUuid } from '../api/authIntent'
import { canonicalPlayJson, playHash } from '../api/terminalPitchWire'
import type { P3ChangeBody } from '../api/pastCorrectionProduct'

const DATABASE = 'pitchlog-p3-product-attempts'
const STORE = 'attempts'
const KEY = ['tenantId', 'gameId']

export type StoredP3Attempt = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d5: string
  deviceId: string
  attemptId: string
  requestJson: string
  requestSha256: string
}>

export class P3AttemptPersistenceError extends Error {
  constructor() {
    super('P3原要求の保存・復元を確認できません')
    this.name = 'P3AttemptPersistenceError'
  }
}

function invalid(): never {
  throw new P3AttemptPersistenceError()
}

function uuid(value: unknown): value is string {
  return typeof value === 'string' && canonicalUuid.test(value)
}

function key(tenantId: string, gameId: string): [string, string] {
  if (!uuid(tenantId) || !uuid(gameId)) invalid()
  return [tenantId, gameId]
}

function completion(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = () => reject(new P3AttemptPersistenceError())
    transaction.onerror = () => reject(new P3AttemptPersistenceError())
  })
}

async function verify(value: unknown, tenantId: string, gameId: string) {
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'attemptId,d4,d5,deviceId,gameId,requestJson,requestSha256,tenantId' ||
    row.tenantId !== tenantId ||
    row.gameId !== gameId ||
    !uuid(row.d5) ||
    !uuid(row.deviceId) ||
    !uuid(row.attemptId) ||
    typeof row.d4 !== 'string' ||
    !/^d4\.1\.[A-Za-z0-9_-]{55}$/.test(row.d4) ||
    typeof row.requestJson !== 'string' ||
    typeof row.requestSha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(row.requestSha256)
  )
    invalid()
  let body: unknown
  try {
    body = JSON.parse(row.requestJson)
  } catch {
    invalid()
  }
  if (
    body === null ||
    typeof body !== 'object' ||
    Array.isArray(body) ||
    Object.keys(body).sort().join(',') !==
      'change,recording_right_proof,recovery_generation'
  )
    invalid()
  const change = (body as Record<string, unknown>).change
  if (
    change === null ||
    typeof change !== 'object' ||
    Array.isArray(change) ||
    Object.keys(change).sort().join(',') !==
      'd5,event_kind,expected_version,game_id,payload,target_reference'
  )
    invalid()
  const event = change as Record<string, unknown>
  const target = event.target_reference
  if (
    event.d5 !== row.d5 ||
    event.game_id !== gameId ||
    event.event_kind !== 'play_change' ||
    event.expected_version !== 1 ||
    target === null ||
    typeof target !== 'object' ||
    Array.isArray(target) ||
    Object.keys(target).sort().join(',') !== 'd1,d4,game' ||
    (target as Record<string, unknown>).game !== gameId ||
    (target as Record<string, unknown>).d4 !== row.d4 ||
    !Number.isSafeInteger((target as Record<string, unknown>).d1) ||
    Number((target as Record<string, unknown>).d1) < 1 ||
    Number((target as Record<string, unknown>).d1) > 25
  )
    invalid()
  try {
    if (
      canonicalPlayJson(body) !== row.requestJson ||
      (await playHash(body)) !== row.requestSha256
    )
      invalid()
  } catch {
    invalid()
  }
  return Object.freeze(row as StoredP3Attempt)
}

/** DB外形が変わったら旧行を成功扱いにせず閉じる。 */
export class P3AttemptPersistence {
  #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(): Promise<P3AttemptPersistence> {
    if (!globalThis.isSecureContext || !globalThis.indexedDB) invalid()
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE, 1)
      let failed = false
      const fail = () => {
        failed = true
        reject(new P3AttemptPersistenceError())
      }
      request.onerror = fail
      request.onblocked = fail
      request.onupgradeneeded = () => {
        try {
          request.result.createObjectStore(STORE, { keyPath: KEY })
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
          if ([...database.objectStoreNames].join(',') !== STORE) invalid()
          const store = database
            .transaction(STORE, 'readonly')
            .objectStore(STORE)
          if (
            JSON.stringify(store.keyPath) !== JSON.stringify(KEY) ||
            store.indexNames.length !== 0
          )
            invalid()
          resolve(new P3AttemptPersistence(database))
        } catch {
          database.close()
          fail()
        }
      }
    })
  }

  async read(
    tenantId: string,
    gameId: string,
  ): Promise<StoredP3Attempt | null> {
    if (this.#closed) invalid()
    const lookup = key(tenantId, gameId)
    const transaction = this.#database.transaction(STORE, 'readonly')
    const done = completion(transaction)
    const request = transaction.objectStore(STORE).get(lookup)
    const raw = await new Promise<unknown>((resolve, reject) => {
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(new P3AttemptPersistenceError())
    })
    await done
    return raw === undefined ? null : verify(raw, tenantId, gameId)
  }

  async prepare(input: {
    tenantId: string
    gameId: string
    deviceId: string
    attemptId: string
    body: P3ChangeBody
  }): Promise<StoredP3Attempt> {
    if (this.#closed) invalid()
    key(input.tenantId, input.gameId)
    if (!uuid(input.deviceId) || !uuid(input.attemptId)) invalid()
    const requestJson = canonicalPlayJson(input.body)
    const requestSha256 = await playHash(input.body)
    const row: StoredP3Attempt = {
      tenantId: input.tenantId,
      gameId: input.gameId,
      d4: input.body.change.target_reference.d4,
      d5: input.body.change.d5,
      deviceId: input.deviceId,
      attemptId: input.attemptId,
      requestJson,
      requestSha256,
    }
    await verify(row, input.tenantId, input.gameId)
    const transaction = this.#database.transaction(STORE, 'readwrite', {
      durability: 'strict',
    })
    if (transaction.durability !== 'strict') {
      transaction.abort()
      invalid()
    }
    const done = completion(transaction)
    transaction.objectStore(STORE).add(row)
    try {
      await done
      return row
    } catch {
      invalid()
    }
  }

  close(): void {
    if (!this.#closed) {
      this.#closed = true
      this.#database.close()
    }
  }
}

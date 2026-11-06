import { canonicalUuid } from '../api/authIntent'
import type { SyncEventRequestBody } from '../api/client.syncEvents'
import type { PlayScreenObservation } from '../screens/GameScreenOrdinaryPitchProvider'
import type { SyncEvent } from './sync/syncEvent'

const DATABASE = 'pitchlog-ordinary-prepared-envelope-v1'
const STORE = 'prepared'
const KEY = ['tenantId', 'gameId', 'd4', 'd1'] as const

export type PreparedEnvelopeKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d1: number
}>

/** 送信前に固定した元要求。V12は保存するが表示・例外へ出さない。 */
export type PreparedEnvelope = PreparedEnvelopeKey &
  Readonly<{
    schemaVersion: 1
    d5: string
    attemptId: string
    observation: PlayScreenObservation
    vocabulary: Readonly<{ tenantId: string; pitchTypeKeys: readonly string[] }>
    event: SyncEvent
    requestBody: SyncEventRequestBody
  }>

export class PreparedEnvelopeError extends Error {
  constructor() {
    super('通常投球の端末準備を確認できません')
    this.name = 'PreparedEnvelopeError'
  }
}

function invalid(): never {
  throw new PreparedEnvelopeError()
}

/** JSONへの黙示的な欠落・getter実行・数値丸めを許さない全値比較用。 */
function canonical(value: unknown, ancestors = new Set<object>()): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || Object.is(value, -0)) invalid()
    return JSON.stringify(value)
  }
  if (typeof value !== 'object' || ancestors.has(value)) invalid()
  if (Object.getOwnPropertySymbols(value).length !== 0) invalid()
  const prototype = Object.getPrototypeOf(value)
  if (
    !Array.isArray(value) &&
    prototype !== Object.prototype &&
    prototype !== null
  )
    invalid()
  ancestors.add(value)
  try {
    if (Array.isArray(value)) {
      if (Object.keys(value).length !== value.length) invalid()
      return (
        '[' +
        value
          .map((_, index) => {
            const descriptor = Object.getOwnPropertyDescriptor(
              value,
              String(index),
            )
            if (!descriptor || !('value' in descriptor)) invalid()
            return canonical(descriptor.value, ancestors)
          })
          .join(',') +
        ']'
      )
    }
    const fields: string[] = []
    for (const name of Object.getOwnPropertyNames(value).sort()) {
      const descriptor = Object.getOwnPropertyDescriptor(value, name)
      if (!descriptor?.enumerable || !('value' in descriptor)) invalid()
      fields.push(
        JSON.stringify(name) + ':' + canonical(descriptor.value, ancestors),
      )
    }
    return '{' + fields.join(',') + '}'
  } finally {
    ancestors.delete(value)
  }
}

function validKey(key: PreparedEnvelopeKey): void {
  if (
    !canonicalUuid.test(key.tenantId) ||
    !canonicalUuid.test(key.gameId) ||
    typeof key.d4 !== 'string' ||
    key.d4.length < 1 ||
    key.d4.length > 128 ||
    !Number.isSafeInteger(key.d1) ||
    key.d1 < 1
  )
    invalid()
}

function checked(value: unknown, key: PreparedEnvelopeKey): PreparedEnvelope {
  canonical(value)
  if (value === null || typeof value !== 'object' || Array.isArray(value))
    invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'attemptId,d1,d4,d5,event,gameId,observation,requestBody,schemaVersion,tenantId,vocabulary' ||
    row.schemaVersion !== 1 ||
    row.tenantId !== key.tenantId ||
    row.gameId !== key.gameId ||
    row.d4 !== key.d4 ||
    row.d1 !== key.d1 ||
    typeof row.d5 !== 'string' ||
    !canonicalUuid.test(row.d5) ||
    typeof row.attemptId !== 'string' ||
    !canonicalUuid.test(row.attemptId)
  )
    invalid()
  const event = row.event as Record<string, unknown> | null
  const fields = event?.fields as Record<string, unknown> | null
  const body = row.requestBody as Record<string, unknown> | null
  const events = body?.events
  const vocabulary = row.vocabulary as Record<string, unknown> | null
  if (
    !event ||
    Object.keys(event).join(',') !== 'fields' ||
    !fields ||
    fields.V1 !== row.d5 ||
    fields.V3 !== key.d4 ||
    fields.V4 !== key.gameId ||
    fields.V5 !== '1' ||
    !Number.isSafeInteger(fields.V6) ||
    (fields.V6 as number) < 1 ||
    !body ||
    Object.keys(body).sort().join(',') !== 'events,recording_right_proof' ||
    body.recording_right_proof === null ||
    !Array.isArray(events) ||
    events.length !== 1 ||
    (events[0] as Record<string, unknown>)?.d1 !== key.d1 ||
    (events[0] as Record<string, unknown>)?.d5 !== row.d5 ||
    (events[0] as Record<string, unknown>)?.d4 !== key.d4 ||
    (events[0] as Record<string, unknown>)?.game_id !== key.gameId ||
    !vocabulary ||
    Object.keys(vocabulary).sort().join(',') !== 'pitchTypeKeys,tenantId' ||
    vocabulary.tenantId !== key.tenantId ||
    !Array.isArray(vocabulary.pitchTypeKeys) ||
    vocabulary.pitchTypeKeys.length === 0 ||
    vocabulary.pitchTypeKeys.some((x) => typeof x !== 'string' || !x) ||
    !row.observation ||
    typeof row.observation !== 'object' ||
    Array.isArray(row.observation)
  )
    invalid()
  return row as PreparedEnvelope
}

/** 1 D1の準備済み原文をstrict保存し、既行の異値上書きを拒否する。 */
export class OrdinaryPreparedEnvelopePersistence {
  readonly #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(): Promise<OrdinaryPreparedEnvelopePersistence> {
    if (
      !globalThis.isSecureContext ||
      typeof globalThis.indexedDB?.open !== 'function'
    )
      invalid()
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE, 1)
      let failed = false
      const fail = () => {
        failed = true
        reject(new PreparedEnvelopeError())
      }
      request.onerror = fail
      request.onblocked = fail
      request.onupgradeneeded = () => {
        try {
          request.result.createObjectStore(STORE, { keyPath: [...KEY] })
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
          const keyPath = database
            .transaction(STORE, 'readonly')
            .objectStore(STORE).keyPath
          if (JSON.stringify(keyPath) !== JSON.stringify(KEY)) invalid()
          resolve(new OrdinaryPreparedEnvelopePersistence(database))
        } catch {
          database.close()
          fail()
        }
      }
    })
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#database.close()
  }

  async read(key: PreparedEnvelopeKey): Promise<PreparedEnvelope | null> {
    return this.#run(key)
  }

  async save(value: PreparedEnvelope): Promise<PreparedEnvelope> {
    const key = {
      tenantId: value.tenantId,
      gameId: value.gameId,
      d4: value.d4,
      d1: value.d1,
    }
    checked(value, key)
    const row = await this.#run(key, value)
    if (!row) invalid()
    return row
  }

  #run(
    key: PreparedEnvelopeKey,
    expected?: PreparedEnvelope,
  ): Promise<PreparedEnvelope | null> {
    validKey(key)
    if (this.#closed) invalid()
    return new Promise((resolve, reject) => {
      let transaction: IDBTransaction
      try {
        transaction = this.#database.transaction(
          STORE,
          expected ? 'readwrite' : 'readonly',
          expected ? { durability: 'strict' } : undefined,
        )
        if (expected && transaction.durability !== 'strict') {
          transaction.abort()
          invalid()
        }
      } catch {
        reject(new PreparedEnvelopeError())
        return
      }
      let ready = false
      let result: PreparedEnvelope | null = null
      const fail = () => {
        try {
          transaction.abort()
        } catch {
          reject(new PreparedEnvelopeError())
        }
      }
      transaction.onabort = () => reject(new PreparedEnvelopeError())
      transaction.onerror = (event) => {
        event.preventDefault()
        fail()
      }
      transaction.oncomplete = () =>
        ready ? resolve(result) : reject(new PreparedEnvelopeError())
      try {
        const store = transaction.objectStore(STORE)
        const request = store.get([key.tenantId, key.gameId, key.d4, key.d1])
        request.onsuccess = () => {
          try {
            if (request.result === undefined) {
              if (expected) {
                store.add(expected)
                result = expected
              }
            } else {
              result = checked(request.result, key)
              if (expected && canonical(result) !== canonical(expected))
                invalid()
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
}

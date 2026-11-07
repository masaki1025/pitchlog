import { canonicalUuid } from '../api/authIntent'

const DATABASE = 'pitchlog-sync-attempt-barrier'
const STORE = 'barriers'
const KEY = ['tenantId', 'gameId', 'd4', 'd5']

type BarrierKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d5: string
}>
export type AttemptBarrier = BarrierKey &
  Readonly<{
    deviceId: string
    originAttemptId: string
    currentAttemptId: string
    bodyJson: string
  }>

export class SyncAttemptBarrierError extends Error {
  constructor() {
    super('元の同期要求と試行を耐久確認できません')
    this.name = 'SyncAttemptBarrierError'
  }
}
function invalid(): never {
  throw new SyncAttemptBarrierError()
}
function secure(): void {
  if (!globalThis.isSecureContext || !globalThis.indexedDB) invalid()
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && canonicalUuid.test(value)
}
/** JSON.stringifyの欠落補修/getter実行を許さず、本文全値を同じ文字列へ写す。 */
function canonical(value: unknown, ancestors = new Set<object>()): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || Object.is(value, -0)) invalid()
    return JSON.stringify(value)
  }
  if (typeof value !== 'object' || ancestors.has(value)) return invalid()
  if (Object.getOwnPropertySymbols(value).length !== 0) return invalid()
  ancestors.add(value)
  try {
    if (Array.isArray(value)) {
      if (Object.keys(value).length !== value.length) return invalid()
      return (
        '[' +
        value
          .map((_, index) => {
            const field = Object.getOwnPropertyDescriptor(value, String(index))
            if (!field || !('value' in field)) return invalid()
            return canonical(field.value, ancestors)
          })
          .join(',') +
        ']'
      )
    }
    const prototype = Object.getPrototypeOf(value)
    if (prototype !== Object.prototype && prototype !== null) return invalid()
    return (
      '{' +
      Object.getOwnPropertyNames(value)
        .sort()
        .map((name) => {
          const field = Object.getOwnPropertyDescriptor(value, name)
          if (!field?.enumerable || !('value' in field)) return invalid()
          return JSON.stringify(name) + ':' + canonical(field.value, ancestors)
        })
        .join(',') +
      '}'
    )
  } finally {
    ancestors.delete(value)
  }
}
function fixed(
  tenantId: string,
  gameId: string,
  body: unknown,
  deviceId: string,
  originAttemptId: string,
): AttemptBarrier {
  if (
    !uuid(tenantId) ||
    !uuid(gameId) ||
    !uuid(deviceId) ||
    !uuid(originAttemptId)
  )
    invalid()
  if (!body || typeof body !== 'object' || Array.isArray(body)) invalid()
  const request = body as Record<string, unknown>
  // getterや欠落補修を実行する前に全原値のJSON表現を確認する。
  const checked = canonical(body)
  const p3 =
    Object.keys(request).sort().join(',') ===
    'change,recording_right_proof,recovery_generation'
  if (
    !p3 &&
    (Object.keys(request).sort().join(',') !== 'events,recording_right_proof' ||
      !Array.isArray(request.events) ||
      request.events.length !== 1)
  )
    invalid()
  const eventValue: unknown = p3
    ? request.change
    : (request.events as unknown[])[0]
  if (
    !eventValue ||
    typeof eventValue !== 'object' ||
    Array.isArray(eventValue)
  )
    invalid()
  const event = eventValue as Record<string, unknown>
  let d4: unknown = event.d4
  if (p3) {
    const target = event.target_reference
    if (
      Object.keys(event).sort().join(',') !==
        'd5,event_kind,expected_version,game_id,payload,target_reference' ||
      event.event_kind !== 'play_change' ||
      typeof request.recovery_generation !== 'string' ||
      !/^[1-9][0-9]*$/.test(request.recovery_generation) ||
      !Number.isSafeInteger(event.expected_version) ||
      typeof event.expected_version !== 'number' ||
      event.expected_version < 1 ||
      !target ||
      typeof target !== 'object' ||
      Array.isArray(target)
    )
      invalid()
    const reference = target as Record<string, unknown>
    if (
      Object.keys(reference).sort().join(',') !== 'd1,d4,game' ||
      reference.game !== gameId ||
      !Number.isSafeInteger(reference.d1) ||
      typeof reference.d1 !== 'number' ||
      reference.d1 < 1
    )
      invalid()
    d4 = reference.d4
  }
  if (
    !uuid(event.d5) ||
    event.game_id !== gameId ||
    typeof d4 !== 'string' ||
    d4.length === 0 ||
    (!p3 &&
      (!Number.isSafeInteger(event.d1) ||
        typeof event.d1 !== 'number' ||
        event.d1 < 1))
  )
    invalid()
  const bodyJson = JSON.stringify(body)
  if (canonical(JSON.parse(bodyJson)) !== checked) invalid()
  return Object.freeze({
    tenantId,
    gameId,
    deviceId,
    d4,
    d5: event.d5,
    originAttemptId,
    currentAttemptId: originAttemptId,
    bodyJson,
  })
}
function read(value: unknown, expected: AttemptBarrier): AttemptBarrier {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    return invalid()
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
      'bodyJson,currentAttemptId,d4,d5,deviceId,gameId,originAttemptId,tenantId' ||
    !KEY.every((name) => row[name] === expected[name as keyof BarrierKey]) ||
    row.deviceId !== expected.deviceId ||
    row.originAttemptId !== expected.originAttemptId ||
    !uuid(row.currentAttemptId) ||
    row.bodyJson !== expected.bodyJson
  )
    invalid()
  return Object.freeze({
    ...expected,
    currentAttemptId: row.currentAttemptId,
  })
}

/** 送信前バリアをstrict IDBに固定し、旧attemptの照会結果だけで更新する。 */
export class SyncAttemptBarrier {
  #database: IDBDatabase
  #closed = false
  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }
  static async open(): Promise<SyncAttemptBarrier> {
    secure()
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DATABASE, 1)
      const fail = () => reject(new SyncAttemptBarrierError())
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
        try {
          if ([...database.objectStoreNames].join(',') !== STORE) invalid()
          const store = database
            .transaction(STORE, 'readonly')
            .objectStore(STORE)
          if (JSON.stringify(store.keyPath) !== JSON.stringify(KEY)) invalid()
          resolve(new SyncAttemptBarrier(database))
        } catch {
          database.close()
          fail()
        }
      }
    })
  }
  close(): void {
    this.#closed = true
    this.#database.close()
  }
  async prepare(
    tenantId: string,
    gameId: string,
    body: unknown,
    deviceId: string,
    originAttemptId: string,
  ): Promise<{ barrier: AttemptBarrier; created: boolean }> {
    const expected = fixed(tenantId, gameId, body, deviceId, originAttemptId)
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction
      try {
        secure()
        if (this.#closed) invalid()
        tx = this.#database.transaction(STORE, 'readwrite', {
          durability: 'strict',
        })
        if (tx.durability !== 'strict') invalid()
      } catch {
        reject(new SyncAttemptBarrierError())
        return
      }
      let result: { barrier: AttemptBarrier; created: boolean } | null = null
      tx.onerror = (event) => event.preventDefault()
      tx.onabort = () => reject(new SyncAttemptBarrierError())
      tx.oncomplete = () =>
        result === null
          ? reject(new SyncAttemptBarrierError())
          : resolve(result)
      const store = tx.objectStore(STORE)
      const request = store.get(
        KEY.map((name) => expected[name as keyof BarrierKey]),
      )
      request.onsuccess = () => {
        try {
          if (request.result === undefined) {
            store.add(expected)
            result = { barrier: expected, created: true }
          } else {
            result = { barrier: read(request.result, expected), created: false }
          }
        } catch {
          tx.abort()
        }
      }
    })
  }
  async advance(
    expected: AttemptBarrier,
    nextAttemptId: string,
  ): Promise<void> {
    if (!uuid(nextAttemptId) || nextAttemptId === expected.currentAttemptId)
      invalid()
    return new Promise((resolve, reject) => {
      let tx: IDBTransaction
      try {
        secure()
        if (this.#closed) invalid()
        tx = this.#database.transaction(STORE, 'readwrite', {
          durability: 'strict',
        })
        if (tx.durability !== 'strict') invalid()
      } catch {
        reject(new SyncAttemptBarrierError())
        return
      }
      let advanced = false
      tx.onerror = (event) => event.preventDefault()
      tx.onabort = () => reject(new SyncAttemptBarrierError())
      tx.oncomplete = () =>
        advanced ? resolve() : reject(new SyncAttemptBarrierError())
      const store = tx.objectStore(STORE)
      const request = store.get(
        KEY.map((name) => expected[name as keyof BarrierKey]),
      )
      request.onsuccess = () => {
        try {
          const current = read(request.result, expected)
          if (current.currentAttemptId !== expected.currentAttemptId) invalid()
          store.put({ ...current, currentAttemptId: nextAttemptId })
          advanced = true
        } catch {
          tx.abort()
        }
      }
    })
  }
}

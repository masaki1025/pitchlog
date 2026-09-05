// この永続化境界は docs/design/sync-protocol.md 7-4 の Q1 の実装である。
// 値の形式は解釈せず、IndexedDB の structured clone にそのまま委ねる。

import {
  prepareTombstoneReplacement,
  type TombstoneBoundaryRequest,
  type TombstoneGenerationInjections,
  type TombstoneGenerationResult,
} from './k5Tombstone'
import {
  queueStateId,
  type I6Acceptance,
  type I6AcceptedResult,
  type QueueActionRequiredLabel,
  type QueueStateId,
} from './queueState'
import {
  isTargetEventReference,
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'

const DATABASE_VERSION = 2
const QUEUE_STORE_NAME = 'queue'
const COUNTER_STORE_NAME = 'd1-counters'
const I6_STORE_NAME = 'i6-results'
const UNSENT_STATE = queueStateId('未送信')
const SYNCED_STATE = queueStateId('同期済み')
const EVACUATED_STATE = queueStateId('退避済み')
const I6_RECEIPT_TOKEN = Symbol('I6 persistence receipt')

type CounterRecord = Readonly<{
  game: unknown
  d4: unknown
  lastD1: number
}>

export type DurableQueueScope = Readonly<{
  game: unknown
  d4: unknown
}>

export type DurableQueueAppend = Readonly<{
  scope: DurableQueueScope
  d5: unknown
  version: unknown
  event: SyncEvent
}>

export type DurableQueueRevisionReplacement = Readonly<{
  kind: 'D7'
  scope: DurableQueueScope
  d1: number
  d5: unknown
  version: unknown
  event: SyncEvent
}>

export type DurableQueueTombstoneOperation = Readonly<{
  kind: 'D6'
  scope: DurableQueueScope
  d1: number
  tombstoneVersion: unknown
  boundaryRequest: TombstoneBoundaryRequest
}>

export type DurableQueueSlot = Readonly<{
  game: unknown
  d4: unknown
  d1: number
  d5: unknown
  version: unknown
  event: SyncEvent
  state: QueueStateId
  actionRequiredLabel?: QueueActionRequiredLabel['id']
}>

export type DurableI6Slot = Readonly<
  I6AcceptedResult & {
    source: 'p3-acceptance'
    state: typeof SYNCED_STATE | typeof EVACUATED_STATE
  }
>

export type I6AcceptedAtResolution =
  | Readonly<{
      known: true
      targetReference: TargetEventReference
      acceptedAt: unknown
    }>
  | Readonly<{ known: false }>

export type I6PersistenceInjections = Readonly<{
  resolveAcceptedAt?: (
    acceptance: I6Acceptance,
  ) => I6AcceptedAtResolution | undefined
}>

export class I6PersistenceReceipt {
  readonly slot: DurableI6Slot
  readonly #acceptance: I6Acceptance

  constructor(slot: DurableI6Slot, token: typeof I6_RECEIPT_TOKEN) {
    if (token !== I6_RECEIPT_TOKEN) {
      throw new Error('I6 の永続化 receipt は直接生成できません')
    }
    this.slot = slot
    this.#acceptance = slot
    Object.freeze(this)
  }

  matches(acceptance: I6Acceptance): boolean {
    return sameI6Operation(this.#acceptance, acceptance)
  }
}

export type D1Allocator = (previousD1: number) => number
export type StoragePersistenceRequester = () => Promise<boolean>

export type DurableQueueOptions = Readonly<{
  databaseName: string
  indexedDbFactory?: IDBFactory | null
  allocateNextD1?: D1Allocator
  requestStoragePersistence?: StoragePersistenceRequester
}>

export class DurableQueueUnavailableError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options)
    this.name = 'DurableQueueUnavailableError'
  }
}

function defaultAllocateNextD1(previousD1: number): number {
  return previousD1 + 1
}

async function defaultRequestStoragePersistence(): Promise<boolean> {
  if (
    typeof navigator === 'undefined' ||
    typeof navigator.storage?.persist !== 'function'
  ) {
    return false
  }
  return navigator.storage.persist()
}

function requestResult<Result>(request: IDBRequest<Result>): Promise<Result> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () =>
      reject(request.error ?? new Error('IndexedDB の要求に失敗しました'))
  })
}

function transactionCompletion(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('IndexedDB の処理を中断しました'))
    transaction.onerror = () => {
      // abort が最終結果を通知するため、ここでは完了を確定しない。
    }
  })
}

function abortTransaction(transaction: IDBTransaction): void {
  try {
    transaction.abort()
  } catch {
    // すでに終了した処理は、その終了理由を呼び出し元へ返す。
  }
}

function indexedDbKey(parts: readonly unknown[]): IDBValidKey {
  return parts as IDBValidKey
}

async function openDatabase(
  databaseName: string,
  factory: IDBFactory,
): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let request: IDBOpenDBRequest
    try {
      request = factory.open(databaseName, DATABASE_VERSION)
    } catch (error) {
      reject(error)
      return
    }

    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(QUEUE_STORE_NAME)) {
        database.createObjectStore(QUEUE_STORE_NAME, {
          keyPath: ['game', 'd4', 'd1'],
        })
      }
      if (!database.objectStoreNames.contains(COUNTER_STORE_NAME)) {
        database.createObjectStore(COUNTER_STORE_NAME, {
          keyPath: ['game', 'd4'],
        })
      }
      if (!database.objectStoreNames.contains(I6_STORE_NAME)) {
        database.createObjectStore(I6_STORE_NAME)
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () =>
      reject(request.error ?? new Error('IndexedDB を開けませんでした'))
    request.onblocked = () =>
      reject(new Error('IndexedDB の開始が阻害されました'))
  })
}

function sameTargetReference(
  first: TargetEventReference,
  second: TargetEventReference,
): boolean {
  return TARGET_EVENT_REFERENCE_ELEMENTS.every((element) =>
    Object.is(first[element], second[element]),
  )
}

function sameI6Operation(first: I6Acceptance, second: I6Acceptance): boolean {
  return (
    sameTargetReference(first.targetReference, second.targetReference) &&
    Object.is(first.d5, second.d5)
  )
}

function i6Key(d5: unknown): IDBValidKey {
  return indexedDbKey([d5])
}

export class DurableQueue {
  readonly storagePersistenceGranted: boolean
  readonly #database: IDBDatabase
  readonly #allocateNextD1: D1Allocator

  constructor(
    database: IDBDatabase,
    storagePersistenceGranted: boolean,
    allocateNextD1: D1Allocator,
  ) {
    this.#database = database
    this.storagePersistenceGranted = storagePersistenceGranted
    this.#allocateNextD1 = allocateNextD1
  }

  async append(input: DurableQueueAppend): Promise<DurableQueueSlot> {
    const transaction = this.#database.transaction(
      [QUEUE_STORE_NAME, COUNTER_STORE_NAME],
      'readwrite',
    )
    const completion = transactionCompletion(transaction)

    try {
      const counterStore = transaction.objectStore(COUNTER_STORE_NAME)
      const queueStore = transaction.objectStore(QUEUE_STORE_NAME)
      const counter = (await requestResult(
        counterStore.get(indexedDbKey([input.scope.game, input.scope.d4])),
      )) as CounterRecord | undefined
      const d1 = this.#allocateNextD1(counter?.lastD1 ?? 0)
      const slot: DurableQueueSlot = {
        game: input.scope.game,
        d4: input.scope.d4,
        d1,
        d5: input.d5,
        version: input.version,
        event: input.event,
        state: UNSENT_STATE,
      }

      counterStore.put({
        game: input.scope.game,
        d4: input.scope.d4,
        lastD1: d1,
      } satisfies CounterRecord)
      queueStore.add(slot)
      await completion
      return slot
    } catch (error) {
      abortTransaction(transaction)
      try {
        await completion
      } catch {
        // 元の失敗を呼び出し元へ返す。
      }
      throw error
    }
  }

  async persistI6Acceptance(
    acceptance: I6Acceptance,
    injections: I6PersistenceInjections = {},
  ): Promise<I6PersistenceReceipt | undefined> {
    if (!isTargetEventReference(acceptance.targetReference)) {
      return undefined
    }

    let resolution: I6AcceptedAtResolution | undefined
    try {
      resolution = injections.resolveAcceptedAt?.(acceptance)
    } catch {
      return undefined
    }
    if (
      !resolution?.known ||
      resolution.acceptedAt === undefined ||
      !isTargetEventReference(resolution.targetReference) ||
      !sameTargetReference(
        acceptance.targetReference,
        resolution.targetReference,
      )
    ) {
      return undefined
    }

    const transaction = this.#database.transaction(I6_STORE_NAME, 'readwrite')
    const completion = transactionCompletion(transaction)
    try {
      const store = transaction.objectStore(I6_STORE_NAME)
      const key = i6Key(acceptance.d5)
      const existing = (await requestResult(store.get(key))) as
        DurableI6Slot | undefined
      if (existing) {
        await completion
        return sameI6Operation(existing, acceptance)
          ? new I6PersistenceReceipt(existing, I6_RECEIPT_TOKEN)
          : undefined
      }

      const slot: DurableI6Slot = {
        ...acceptance,
        acceptedAt: resolution.acceptedAt,
        source: 'p3-acceptance',
        state: SYNCED_STATE,
      }
      store.add(slot, key)
      await completion
      return new I6PersistenceReceipt(slot, I6_RECEIPT_TOKEN)
    } catch (error) {
      abortTransaction(transaction)
      try {
        await completion
      } catch {
        // 元の失敗を呼び出し元へ返す。
      }
      throw error
    }
  }

  async readI6(d5: unknown): Promise<DurableI6Slot | undefined> {
    const transaction = this.#database.transaction(I6_STORE_NAME, 'readonly')
    const completion = transactionCompletion(transaction)
    const slot = (await requestResult(
      transaction.objectStore(I6_STORE_NAME).get(i6Key(d5)),
    )) as DurableI6Slot | undefined
    await completion
    return slot
  }

  async evacuateI6(d5: unknown): Promise<DurableI6Slot | undefined> {
    const transaction = this.#database.transaction(I6_STORE_NAME, 'readwrite')
    const completion = transactionCompletion(transaction)
    try {
      const store = transaction.objectStore(I6_STORE_NAME)
      const key = i6Key(d5)
      const existing = (await requestResult(store.get(key))) as
        DurableI6Slot | undefined
      if (!existing) {
        await completion
        return undefined
      }
      const evacuated: DurableI6Slot = {
        ...existing,
        state: EVACUATED_STATE,
      }
      store.put(evacuated, key)
      await completion
      return evacuated
    } catch (error) {
      abortTransaction(transaction)
      try {
        await completion
      } catch {
        // 元の失敗を呼び出し元へ返す。
      }
      throw error
    }
  }

  async replaceRevision(
    input: DurableQueueRevisionReplacement,
  ): Promise<DurableQueueSlot> {
    if (input.kind !== 'D7') {
      throw new Error('改訂版以外はローカル置換できません')
    }
    const transaction = this.#database.transaction(
      QUEUE_STORE_NAME,
      'readwrite',
    )
    const completion = transactionCompletion(transaction)

    try {
      const store = transaction.objectStore(QUEUE_STORE_NAME)
      const existing = (await requestResult(
        store.get(indexedDbKey([input.scope.game, input.scope.d4, input.d1])),
      )) as DurableQueueSlot | undefined
      if (!existing) {
        throw new Error('置換対象のキュースロットがありません')
      }

      const replacement: DurableQueueSlot = {
        game: existing.game,
        d4: existing.d4,
        d1: existing.d1,
        d5: input.d5,
        version: input.version,
        event: input.event,
        state: UNSENT_STATE,
      }
      store.put(replacement)
      await completion
      return replacement
    } catch (error) {
      abortTransaction(transaction)
      try {
        await completion
      } catch {
        // 元の失敗を呼び出し元へ返す。
      }
      throw error
    }
  }

  async replaceWithTombstone(
    input: DurableQueueTombstoneOperation,
    injections: TombstoneGenerationInjections = {},
  ): Promise<TombstoneGenerationResult> {
    if (input.kind !== 'D6') {
      throw new Error('墓標以外は K5 の置換対象にできません')
    }
    const transaction = this.#database.transaction(
      QUEUE_STORE_NAME,
      'readwrite',
    )
    const completion = transactionCompletion(transaction)

    try {
      const store = transaction.objectStore(QUEUE_STORE_NAME)
      const existing = (await requestResult(
        store.get(indexedDbKey([input.scope.game, input.scope.d4, input.d1])),
      )) as DurableQueueSlot | undefined
      if (!existing) {
        throw new Error('墓標置換対象のキュースロットがありません')
      }

      const prepared = prepareTombstoneReplacement(
        {
          slot: existing,
          tombstoneVersion: input.tombstoneVersion,
          boundaryRequest: input.boundaryRequest,
        },
        injections,
      )
      if (!prepared.offered) {
        await completion
        return prepared
      }

      store.put(prepared.replacement)
      await completion
      return prepared
    } catch (error) {
      abortTransaction(transaction)
      try {
        await completion
      } catch {
        // 元の失敗を呼び出し元へ返す。
      }
      throw error
    }
  }

  async readSlot(
    scope: DurableQueueScope,
    d1: number,
  ): Promise<DurableQueueSlot | undefined> {
    const transaction = this.#database.transaction(QUEUE_STORE_NAME, 'readonly')
    const completion = transactionCompletion(transaction)
    const slot = (await requestResult(
      transaction
        .objectStore(QUEUE_STORE_NAME)
        .get(indexedDbKey([scope.game, scope.d4, d1])),
    )) as DurableQueueSlot | undefined
    await completion
    return slot
  }

  async countSlots(): Promise<number> {
    const transaction = this.#database.transaction(QUEUE_STORE_NAME, 'readonly')
    const completion = transactionCompletion(transaction)
    const count = await requestResult(
      transaction.objectStore(QUEUE_STORE_NAME).count(),
    )
    await completion
    return count
  }

  async readNextD1(scope: DurableQueueScope): Promise<number> {
    const transaction = this.#database.transaction(
      COUNTER_STORE_NAME,
      'readonly',
    )
    const completion = transactionCompletion(transaction)
    const counter = (await requestResult(
      transaction
        .objectStore(COUNTER_STORE_NAME)
        .get(indexedDbKey([scope.game, scope.d4])),
    )) as CounterRecord | undefined
    await completion
    return this.#allocateNextD1(counter?.lastD1 ?? 0)
  }

  close(): void {
    this.#database.close()
  }
}

export async function openDurableQueue(
  options: DurableQueueOptions,
): Promise<DurableQueue> {
  const factory =
    options.indexedDbFactory === undefined
      ? typeof indexedDB === 'undefined'
        ? undefined
        : indexedDB
      : options.indexedDbFactory
  if (!factory) {
    throw new DurableQueueUnavailableError('IndexedDB を利用できません')
  }

  let database: IDBDatabase
  try {
    database = await openDatabase(options.databaseName, factory)
  } catch (error) {
    throw new DurableQueueUnavailableError('IndexedDB を開始できません', {
      cause: error,
    })
  }

  const requestStoragePersistence =
    options.requestStoragePersistence ?? defaultRequestStoragePersistence
  let storagePersistenceGranted = false
  try {
    storagePersistenceGranted = (await requestStoragePersistence()) === true
  } catch {
    storagePersistenceGranted = false
  }

  return new DurableQueue(
    database,
    storagePersistenceGranted,
    options.allocateNextD1 ?? defaultAllocateNextD1,
  )
}

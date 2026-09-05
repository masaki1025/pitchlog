// この永続化境界は docs/design/sync-protocol.md 7-4 の Q1 の実装である。
// 値の形式は解釈せず、IndexedDB の structured clone にそのまま委ねる。

import {
  prepareTombstoneReplacement as evaluateTombstoneReplacement,
  type TombstoneBoundaryRequest,
  type TombstoneGenerationInjections,
  type TombstoneGenerationResult,
} from './k5Tombstone'
import { EVENT_KIND_SLOT_ID } from './eventFieldRules'
import { EVENT_KIND_RULES } from './eventKinds'
import {
  checkMappingConfirmation,
  type MappingConfirmationInjections,
} from './mappingConfirmationGate'
import {
  actionRequiredLabelId,
  queueStateId,
  type I6Acceptance,
  type I6AcceptedResult,
  type QueueActionRequiredLabel,
  type QueueStateId,
} from './queueState'
import {
  evaluateQueueTransition,
  type QueueTransitionInjections,
} from './queueTransition'
import {
  isTargetEventReference,
  TARGET_EVENT_REFERENCE_ELEMENTS,
  type SyncEvent,
  type TargetEventReference,
} from './syncEvent'

const DATABASE_VERSION = 3
const QUEUE_STORE_NAME = 'queue'
const QUEUE_STATE_INDEX_NAME = 'queue-by-state'
const COUNTER_STORE_NAME = 'd1-counters'
const I6_STORE_NAME = 'i6-results'
const UNSENT_STATE = queueStateId('未送信')
const ACTION_REQUIRED_STATE = queueStateId('要操作')
const SYNCED_STATE = queueStateId('同期済み')
const EVACUATED_STATE = queueStateId('退避済み')
const REVISION_ACTION_LABEL_ID = actionRequiredLabelId('改訂待ち')
const REVISION_EVENT_KIND = EVENT_KIND_RULES.find(
  (eventKind) => eventKind.name === '改訂版',
)
if (!REVISION_EVENT_KIND) {
  throw new Error('改訂版のイベント種別がありません')
}
const REVISION_EVENT_KIND_ID = REVISION_EVENT_KIND.id
const PREPARATION_TOKEN = Symbol('durable queue preparation')
const I6_RECEIPT_TOKEN = Symbol('I6 persistence receipt')
const I6_EVACUATION_RECEIPT_TOKEN = Symbol('I6 evacuation receipt')
const PREPARATION_STATE = {
  FRESH: 'fresh',
  IN_FLIGHT: 'in-flight',
  CONSUMED: 'consumed',
} as const

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

export type I6EvacuationInjections = Readonly<{
  confirmI6EvacuationSaved?: (slot: DurableI6Slot) => boolean | undefined
}>

type DurableQueuePreparationKind =
  | 'append'
  | 'a5-transition'
  | 'i6-persistence'
  | 'revision-replacement'
  | 'tombstone-replacement'

type DurableA5TransitionSnapshot = Readonly<{
  slot: Readonly<{
    state: typeof UNSENT_STATE
    source: 'd1-event'
    key: Readonly<{
      d4: unknown
      d1: number
      d5: unknown
    }>
    content: SyncEvent
  }>
  allowsSyncedTransition: boolean
}>

type DurableA5TransitionTarget = Readonly<{
  game: unknown
  d4: unknown
  d1: number
  d5: unknown
}>

type DurableA5TransitionInjections = MappingConfirmationInjections &
  QueueTransitionInjections

type DurableQueuePreparedPayload =
  | Readonly<{
      kind: 'append'
      input: DurableQueueAppend
    }>
  | Readonly<{
      kind: 'a5-transition'
      snapshot: DurableA5TransitionSnapshot
      target: DurableA5TransitionTarget
      injections: DurableA5TransitionInjections
    }>
  | Readonly<{
      kind: 'i6-persistence'
      slot: DurableI6Slot
    }>
  | Readonly<{
      kind: 'revision-replacement'
      input: DurableQueueRevisionReplacement
    }>
  | Readonly<{
      kind: 'tombstone-replacement'
      input: DurableQueueTombstoneOperation
      injections: TombstoneGenerationInjections
    }>

type PreparationState =
  (typeof PREPARATION_STATE)[keyof typeof PREPARATION_STATE]

type PreparedPayloadRecord = {
  readonly owner: object
  readonly payload: DurableQueuePreparedPayload
  state: PreparationState
}

const PREPARED_PAYLOADS = new WeakMap<
  DurableQueuePreparation,
  PreparedPayloadRecord
>()

export class DurableQueuePreparation<
  Kind extends DurableQueuePreparationKind = DurableQueuePreparationKind,
> {
  readonly #kind: Kind

  constructor(token: typeof PREPARATION_TOKEN, kind: Kind) {
    if (token !== PREPARATION_TOKEN) {
      throw new Error('永続キューの preparation は直接生成できません')
    }
    this.#kind = kind
    Object.freeze(this)
  }

  static consumeA5(
    preparation: DurableQueuePreparation<'a5-transition'> | undefined,
    owner: object,
  ): DurableA5TransitionSnapshot | undefined {
    if (!preparation) {
      return undefined
    }

    let record: PreparedPayloadRecord
    try {
      if (preparation.#kind !== 'a5-transition') {
        return undefined
      }
      record = beginPreparation(preparation, 'a5-transition', owner)
    } catch {
      return undefined
    }
    try {
      const payload = record.payload
      return payload.kind === 'a5-transition'
        ? structuredClone(payload.snapshot)
        : undefined
    } finally {
      record.state = PREPARATION_STATE.CONSUMED
    }
  }
}

function createPreparation<Kind extends DurableQueuePreparationKind>(
  payload: Extract<DurableQueuePreparedPayload, { kind: Kind }>,
  owner: object,
): DurableQueuePreparation<Kind> {
  const preparation = new DurableQueuePreparation<Kind>(
    PREPARATION_TOKEN,
    payload.kind,
  )
  PREPARED_PAYLOADS.set(preparation, {
    owner,
    payload,
    state: PREPARATION_STATE.FRESH,
  })
  return preparation
}

function beginPreparation<Kind extends DurableQueuePreparationKind>(
  preparation: DurableQueuePreparation<Kind>,
  kind: Kind,
  owner?: object,
): PreparedPayloadRecord & {
  readonly payload: Extract<DurableQueuePreparedPayload, { kind: Kind }>
} {
  const record = PREPARED_PAYLOADS.get(preparation)
  if (
    !record ||
    record.payload.kind !== kind ||
    (owner !== undefined && record.owner !== owner) ||
    record.state !== PREPARATION_STATE.FRESH
  ) {
    throw new Error('永続キューの変更に必要な preparation が不正です')
  }
  record.state = PREPARATION_STATE.IN_FLIGHT
  return record as PreparedPayloadRecord & {
    readonly payload: Extract<DurableQueuePreparedPayload, { kind: Kind }>
  }
}

async function usePreparation<Kind extends DurableQueuePreparationKind, Result>(
  preparation: DurableQueuePreparation<Kind>,
  kind: Kind,
  owner: object,
  operation: (
    payload: Extract<DurableQueuePreparedPayload, { kind: Kind }>,
  ) => Promise<Result>,
): Promise<Result> {
  const record = beginPreparation(preparation, kind, owner)
  try {
    return await operation(record.payload)
  } finally {
    record.state = PREPARATION_STATE.CONSUMED
  }
}

type I6ReceiptPayload = Readonly<{
  slot: DurableI6Slot
  owner: object
}>

const I6_PERSISTENCE_RECEIPTS = new WeakMap<
  I6PersistenceReceipt,
  I6ReceiptPayload
>()

export class I6PersistenceReceipt {
  constructor(
    slot: DurableI6Slot,
    token: typeof I6_RECEIPT_TOKEN,
    owner?: object,
  ) {
    if (token !== I6_RECEIPT_TOKEN) {
      throw new Error('I6 の永続化 receipt は直接生成できません')
    }
    I6_PERSISTENCE_RECEIPTS.set(this, {
      slot: structuredClone(slot),
      owner: owner ?? this,
    })
  }

  static verify(
    receipt: I6PersistenceReceipt | undefined,
  ): DurableI6Slot | undefined {
    return verifiedReceiptSlot(I6_PERSISTENCE_RECEIPTS, receipt)
  }

  get slot(): DurableI6Slot {
    const payload = I6_PERSISTENCE_RECEIPTS.get(this)
    if (!payload) {
      throw new Error('I6 の永続化 receipt が不正です')
    }
    return structuredClone(payload.slot)
  }

  matches(result: I6AcceptedResult): boolean {
    const payload = I6_PERSISTENCE_RECEIPTS.get(this)
    return payload ? sameI6Result(payload.slot, result) : false
  }
}

const I6_EVACUATION_RECEIPTS = new WeakMap<
  I6EvacuationReceipt,
  I6ReceiptPayload
>()

export class I6EvacuationReceipt {
  constructor(
    slot: DurableI6Slot,
    token: typeof I6_EVACUATION_RECEIPT_TOKEN,
    owner?: object,
  ) {
    if (token !== I6_EVACUATION_RECEIPT_TOKEN) {
      throw new Error('I6 の退避保存 receipt は直接生成できません')
    }
    I6_EVACUATION_RECEIPTS.set(this, {
      slot: structuredClone(slot),
      owner: owner ?? this,
    })
  }

  static verify(
    receipt: I6EvacuationReceipt | undefined,
  ): DurableI6Slot | undefined {
    return verifiedReceiptSlot(I6_EVACUATION_RECEIPTS, receipt)
  }

  get slot(): DurableI6Slot {
    const payload = I6_EVACUATION_RECEIPTS.get(this)
    if (!payload) {
      throw new Error('I6 の退避保存 receipt が不正です')
    }
    return structuredClone(payload.slot)
  }

  matches(result: I6AcceptedResult): boolean {
    const payload = I6_EVACUATION_RECEIPTS.get(this)
    return payload ? sameI6Result(payload.slot, result) : false
  }
}

function verifiedReceiptSlot<Receipt extends object>(
  receipts: WeakMap<Receipt, I6ReceiptPayload>,
  receipt: Receipt | undefined,
): DurableI6Slot | undefined {
  const payload = verifiedReceiptPayload(receipts, receipt)
  return payload ? structuredClone(payload.slot) : undefined
}

function verifiedReceiptPayload<Receipt extends object>(
  receipts: WeakMap<Receipt, I6ReceiptPayload>,
  receipt: Receipt | undefined,
): I6ReceiptPayload | undefined {
  if (!receipt) {
    return undefined
  }
  const payload = receipts.get(receipt)
  return payload && !Object.hasOwn(receipt, 'slot') ? payload : undefined
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
      const upgradeTransaction = request.transaction
      if (!upgradeTransaction) {
        throw new Error('IndexedDB の更新トランザクションがありません')
      }
      const queueStore = database.objectStoreNames.contains(QUEUE_STORE_NAME)
        ? upgradeTransaction.objectStore(QUEUE_STORE_NAME)
        : database.createObjectStore(QUEUE_STORE_NAME, {
            keyPath: ['game', 'd4', 'd1'],
          })
      if (!queueStore.indexNames.contains(QUEUE_STATE_INDEX_NAME)) {
        queueStore.createIndex(QUEUE_STATE_INDEX_NAME, 'state')
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

function sameI6Result(
  first: I6AcceptedResult,
  second: I6AcceptedResult,
): boolean {
  return (
    sameTargetReference(first.targetReference, second.targetReference) &&
    Object.is(first.expectedVersion, second.expectedVersion) &&
    Object.is(first.d5, second.d5) &&
    Object.is(first.confirmedContent, second.confirmedContent) &&
    Object.is(first.acceptedAt, second.acceptedAt)
  )
}

function isRevisionEvent(event: SyncEvent): boolean {
  return (
    typeof event === 'object' &&
    event !== null &&
    typeof event.fields === 'object' &&
    event.fields !== null &&
    Reflect.ownKeys(event.fields).length > 0 &&
    Object.is(event.fields[EVENT_KIND_SLOT_ID], REVISION_EVENT_KIND_ID)
  )
}

function eventKindFor(event: SyncEvent) {
  if (
    typeof event === 'object' &&
    event !== null &&
    typeof event.fields === 'object' &&
    event.fields !== null
  ) {
    return EVENT_KIND_RULES.find((eventKind) =>
      Object.is(event.fields[EVENT_KIND_SLOT_ID], eventKind.id),
    )
  }
  return undefined
}

function i6Key(d5: unknown): IDBValidKey {
  return indexedDbKey([d5])
}

function matchesA5Target(
  slot: DurableQueueSlot,
  target: DurableA5TransitionTarget,
  snapshot: DurableA5TransitionSnapshot,
): boolean {
  return (
    slot.state === UNSENT_STATE &&
    Object.is(slot.game, target.game) &&
    Object.is(slot.d4, target.d4) &&
    Object.is(slot.d1, target.d1) &&
    Object.is(slot.d5, target.d5) &&
    Object.is(snapshot.slot.key.d4, target.d4) &&
    Object.is(snapshot.slot.key.d1, target.d1) &&
    Object.is(snapshot.slot.key.d5, target.d5)
  )
}

function persistedA5Slot(
  existing: DurableQueueSlot,
  transitioned: ReturnType<typeof evaluateQueueTransition>,
): DurableQueueSlot | undefined {
  if (
    !transitioned.applied ||
    !transitioned.slot ||
    transitioned.slot.source !== 'd1-event' ||
    !Object.is(transitioned.slot.key.d4, existing.d4) ||
    !Object.is(transitioned.slot.key.d1, existing.d1) ||
    !Object.is(transitioned.slot.key.d5, existing.d5)
  ) {
    return undefined
  }

  return {
    game: existing.game,
    d4: existing.d4,
    d1: existing.d1,
    d5: existing.d5,
    version: existing.version,
    event: existing.event,
    state: transitioned.slot.state,
    ...(transitioned.slot.actionRequiredLabel === undefined
      ? {}
      : { actionRequiredLabel: transitioned.slot.actionRequiredLabel }),
  }
}

export class DurableQueue {
  readonly storagePersistenceGranted: boolean
  readonly #database: IDBDatabase
  readonly #allocateNextD1: D1Allocator
  readonly #credentialOwner = Object.freeze({})

  constructor(
    database: IDBDatabase,
    storagePersistenceGranted: boolean,
    allocateNextD1: D1Allocator,
  ) {
    this.#database = database
    this.storagePersistenceGranted = storagePersistenceGranted
    this.#allocateNextD1 = allocateNextD1
  }

  prepareAppend(input: DurableQueueAppend): DurableQueuePreparation<'append'> {
    return createPreparation(
      {
        kind: 'append',
        input: structuredClone(input),
      },
      this.#credentialOwner,
    )
  }

  async append(
    preparation: DurableQueuePreparation<'append'>,
  ): Promise<DurableQueueSlot> {
    return usePreparation(
      preparation,
      'append',
      this.#credentialOwner,
      async ({ input }) => {
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
      },
    )
  }

  async prepareA5Transition(
    scope: DurableQueueScope,
    d1: number,
    injections: DurableA5TransitionInjections = {},
  ): Promise<DurableQueuePreparation<'a5-transition'> | undefined> {
    const transaction = this.#database.transaction(QUEUE_STORE_NAME, 'readonly')
    const completion = transactionCompletion(transaction)
    const slot = (await requestResult(
      transaction
        .objectStore(QUEUE_STORE_NAME)
        .get(indexedDbKey([scope.game, scope.d4, d1])),
    )) as DurableQueueSlot | undefined
    if (!slot || slot.state !== UNSENT_STATE) {
      await completion
      return undefined
    }
    const eventKind = eventKindFor(slot.event)
    if (!eventKind) {
      await completion
      return undefined
    }
    const mappingConfirmation = checkMappingConfirmation(
      { eventKind, event: slot.event },
      injections,
    )
    await completion
    return createPreparation(
      {
        kind: 'a5-transition',
        target: {
          game: slot.game,
          d4: slot.d4,
          d1: slot.d1,
          d5: slot.d5,
        },
        snapshot: {
          slot: {
            state: UNSENT_STATE,
            source: 'd1-event',
            key: { d4: slot.d4, d1: slot.d1, d5: slot.d5 },
            content: slot.event,
          },
          allowsSyncedTransition: mappingConfirmation.allowsSyncedTransition,
        },
        injections: Object.freeze({ ...injections }),
      },
      this.#credentialOwner,
    )
  }

  async persistA5Transition(
    preparation: DurableQueuePreparation<'a5-transition'>,
  ): Promise<DurableQueueSlot | undefined> {
    return usePreparation(
      preparation,
      'a5-transition',
      this.#credentialOwner,
      async ({ target, snapshot, injections }) => {
        const transaction = this.#database.transaction(
          QUEUE_STORE_NAME,
          'readwrite',
        )
        const completion = transactionCompletion(transaction)

        try {
          const store = transaction.objectStore(QUEUE_STORE_NAME)
          const existing = (await requestResult(
            store.get(indexedDbKey([target.game, target.d4, target.d1])),
          )) as DurableQueueSlot | undefined
          if (!existing || !matchesA5Target(existing, target, snapshot)) {
            await completion
            return undefined
          }

          // 状態の決定は 7-2 の単一実装へ委ね、永続境界では結果だけを書き込む。
          const evaluationPreparation = createPreparation(
            {
              kind: 'a5-transition',
              target,
              snapshot,
              injections,
            },
            this.#credentialOwner,
          )
          const transitioned = evaluateQueueTransition(
            {
              kind: 'apply-a5',
              queue: this,
              preparation: evaluationPreparation,
            },
            injections,
          )
          const persisted = persistedA5Slot(existing, transitioned)
          if (!persisted) {
            await completion
            return undefined
          }

          store.put(persisted)
          await completion
          return persisted
        } catch (error) {
          abortTransaction(transaction)
          try {
            await completion
          } catch {
            // 元の失敗を呼び出し元へ返す。
          }
          throw error
        }
      },
    )
  }

  consumeA5Preparation(
    preparation: DurableQueuePreparation<'a5-transition'>,
  ): DurableA5TransitionSnapshot | undefined {
    return DurableQueuePreparation.consumeA5(preparation, this.#credentialOwner)
  }

  prepareI6Acceptance(
    acceptance: I6Acceptance,
    injections: I6PersistenceInjections = {},
  ): DurableQueuePreparation<'i6-persistence'> | undefined {
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

    return createPreparation(
      {
        kind: 'i6-persistence',
        slot: structuredClone({
          ...acceptance,
          acceptedAt: resolution.acceptedAt,
          source: 'p3-acceptance',
          state: SYNCED_STATE,
        } satisfies DurableI6Slot),
      },
      this.#credentialOwner,
    )
  }

  async persistI6Acceptance(
    preparation: DurableQueuePreparation<'i6-persistence'>,
  ): Promise<I6PersistenceReceipt | undefined> {
    return usePreparation(
      preparation,
      'i6-persistence',
      this.#credentialOwner,
      async ({ slot }) => {
        const transaction = this.#database.transaction(
          I6_STORE_NAME,
          'readwrite',
        )
        const completion = transactionCompletion(transaction)
        try {
          const store = transaction.objectStore(I6_STORE_NAME)
          const key = i6Key(slot.d5)
          const existing = (await requestResult(store.get(key))) as
            DurableI6Slot | undefined
          if (existing) {
            await completion
            return existing.state === SYNCED_STATE &&
              sameI6Result(existing, slot)
              ? new I6PersistenceReceipt(
                  existing,
                  I6_RECEIPT_TOKEN,
                  this.#credentialOwner,
                )
              : undefined
          }

          store.add(slot, key)
          await completion
          return new I6PersistenceReceipt(
            slot,
            I6_RECEIPT_TOKEN,
            this.#credentialOwner,
          )
        } catch (error) {
          abortTransaction(transaction)
          try {
            await completion
          } catch {
            // 元の失敗を呼び出し元へ返す。
          }
          throw error
        }
      },
    )
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

  async prepareI6Evacuation(
    d5: unknown,
    injections: I6EvacuationInjections = {},
  ): Promise<I6EvacuationReceipt | undefined> {
    const slot = await this.readI6(d5)
    if (!slot || slot.state !== SYNCED_STATE) {
      return undefined
    }

    let saved: boolean | undefined
    try {
      saved = injections.confirmI6EvacuationSaved?.(structuredClone(slot))
    } catch {
      return undefined
    }
    return saved === true
      ? new I6EvacuationReceipt(
          slot,
          I6_EVACUATION_RECEIPT_TOKEN,
          this.#credentialOwner,
        )
      : undefined
  }

  async evacuateI6(
    receipt: I6EvacuationReceipt,
  ): Promise<DurableI6Slot | undefined> {
    const receiptPayload = verifiedReceiptPayload(
      I6_EVACUATION_RECEIPTS,
      receipt,
    )
    if (!receiptPayload || receiptPayload.owner !== this.#credentialOwner) {
      throw new Error('I6 の退避保存 receipt が不正です')
    }
    const transaction = this.#database.transaction(I6_STORE_NAME, 'readwrite')
    const completion = transactionCompletion(transaction)
    try {
      const store = transaction.objectStore(I6_STORE_NAME)
      const key = i6Key(receiptPayload.slot.d5)
      const existing = (await requestResult(store.get(key))) as
        DurableI6Slot | undefined
      if (
        !existing ||
        existing.state !== SYNCED_STATE ||
        !sameI6Result(existing, receiptPayload.slot)
      ) {
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

  prepareRevisionReplacement(
    input: DurableQueueRevisionReplacement,
  ): DurableQueuePreparation<'revision-replacement'> {
    const clonedInput = structuredClone(input)
    if (!isRevisionEvent(clonedInput.event)) {
      throw new Error('実際の改訂版イベントだけを準備できます')
    }
    return createPreparation(
      {
        kind: 'revision-replacement',
        input: clonedInput,
      },
      this.#credentialOwner,
    )
  }

  async replaceRevision(
    preparation: DurableQueuePreparation<'revision-replacement'>,
  ): Promise<DurableQueueSlot> {
    return usePreparation(
      preparation,
      'revision-replacement',
      this.#credentialOwner,
      async ({ input }) => {
        const transaction = this.#database.transaction(
          QUEUE_STORE_NAME,
          'readwrite',
        )
        const completion = transactionCompletion(transaction)

        try {
          const store = transaction.objectStore(QUEUE_STORE_NAME)
          const existing = (await requestResult(
            store.get(
              indexedDbKey([input.scope.game, input.scope.d4, input.d1]),
            ),
          )) as DurableQueueSlot | undefined
          if (!existing) {
            throw new Error('置換対象のキュースロットがありません')
          }
          if (
            existing.state !== ACTION_REQUIRED_STATE ||
            existing.actionRequiredLabel !== REVISION_ACTION_LABEL_ID
          ) {
            throw new Error('改訂待ちの要操作スロットだけを置換できます')
          }
          if (input.d5 === undefined || Object.is(existing.d5, input.d5)) {
            throw new Error('改訂版には新しい D5 が必要です')
          }
          if (!isRevisionEvent(input.event)) {
            throw new Error('実際の改訂版イベントだけを置換できます')
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
      },
    )
  }

  prepareTombstoneReplacement(
    input: DurableQueueTombstoneOperation,
    injections: TombstoneGenerationInjections = {},
  ): DurableQueuePreparation<'tombstone-replacement'> {
    if (input.kind !== 'D6') {
      throw new Error('墓標以外は K5 の置換対象にできません')
    }
    return createPreparation(
      {
        kind: 'tombstone-replacement',
        input: structuredClone(input),
        injections: Object.freeze({ ...injections }),
      },
      this.#credentialOwner,
    )
  }

  async replaceWithTombstone(
    preparation: DurableQueuePreparation<'tombstone-replacement'>,
  ): Promise<TombstoneGenerationResult> {
    return usePreparation(
      preparation,
      'tombstone-replacement',
      this.#credentialOwner,
      async ({ input, injections }) => {
        const transaction = this.#database.transaction(
          QUEUE_STORE_NAME,
          'readwrite',
        )
        const completion = transactionCompletion(transaction)

        try {
          const store = transaction.objectStore(QUEUE_STORE_NAME)
          const existing = (await requestResult(
            store.get(
              indexedDbKey([input.scope.game, input.scope.d4, input.d1]),
            ),
          )) as DurableQueueSlot | undefined
          if (!existing) {
            throw new Error('墓標置換対象のキュースロットがありません')
          }

          const prepared = evaluateTombstoneReplacement(
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
      },
    )
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

  async countUnsentSlots(): Promise<number> {
    const transaction = this.#database.transaction(QUEUE_STORE_NAME, 'readonly')
    const completion = transactionCompletion(transaction)
    const count = await requestResult(
      transaction
        .objectStore(QUEUE_STORE_NAME)
        .index(QUEUE_STATE_INDEX_NAME)
        .count(UNSENT_STATE),
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

type DurableQueuePublicMethodRule =
  | Readonly<{ effect: 'read' | 'prepare' | 'lifecycle' }>
  | Readonly<{
      effect: 'mutation'
      boundary: 'preparation' | 'receipt'
    }>

export const DURABLE_QUEUE_PUBLIC_METHOD_RULES = {
  prepareAppend: { effect: 'prepare' },
  append: { effect: 'mutation', boundary: 'preparation' },
  prepareA5Transition: { effect: 'prepare' },
  persistA5Transition: { effect: 'mutation', boundary: 'preparation' },
  consumeA5Preparation: { effect: 'prepare' },
  prepareI6Acceptance: { effect: 'prepare' },
  persistI6Acceptance: { effect: 'mutation', boundary: 'preparation' },
  readI6: { effect: 'read' },
  prepareI6Evacuation: { effect: 'prepare' },
  evacuateI6: { effect: 'mutation', boundary: 'receipt' },
  prepareRevisionReplacement: { effect: 'prepare' },
  replaceRevision: { effect: 'mutation', boundary: 'preparation' },
  prepareTombstoneReplacement: { effect: 'prepare' },
  replaceWithTombstone: { effect: 'mutation', boundary: 'preparation' },
  readSlot: { effect: 'read' },
  countSlots: { effect: 'read' },
  countUnsentSlots: { effect: 'read' },
  readNextD1: { effect: 'read' },
  close: { effect: 'lifecycle' },
} as const satisfies Readonly<
  Record<
    Exclude<keyof DurableQueue, 'storagePersistenceGranted'>,
    DurableQueuePublicMethodRule
  >
>

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

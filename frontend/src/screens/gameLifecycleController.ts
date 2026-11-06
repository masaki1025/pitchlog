// 終了・追記再開の実画面controller（接続版）。
//
// 順序は docs/features/mvp-lifecycle-ui-connection/plan.md の固定に従う:
//   1. 単一書き手の排他を待たずに取る（実preconditionsをhostから注入する）
//   2. 端末に保持した「最後に実GETで確認したbase」と耐久queueのchainから、
//      現在の期待statusと checkpointRef / target を導出する
//   3. D5/D1/D2/予約event/receipt/attempt/V12込み全本文を IndexedDB へ strict commit
//   4. 既存 queue へ追記し、追記が成立した時点を受理とする
//   5. 先行の未終結slotがあれば送信せず、順序が来た再送で同じ本文を送る
//   6. 既存 ACK 機構で同 slot の受理/重複だけを同期済みへ
//   7. ACK後の実GETが「ACK対象の確定版/receipt またはそれ以後」を示した時だけ
//      再取得済みとする。古いGETは採用しない。
//
// 通信断中でも終了→再開→再終了を耐久queueへ積める。baseは実GET成功時だけ更新し、
// 未確定の要求をTTLで捨てたり新D5へ置換したりしない。
import {
  buildGameLifecyclePayload,
  buildGameLifecycleRequestBody,
  buildGameLifecycleSyncEvent,
  gameLifecycleEventKind,
  isGameLifecycleRequestBody,
  postGameLifecycleRequestBody,
  readGameLifecycle,
  type GameLifecycleAction,
  type GameLifecycleCheckpointRef,
  type GameLifecycleGame,
  type GameLifecycleReopenTarget,
  type GameLifecycleRequestBody,
  type GameLifecycleStatus,
  type GameLifecycleTarget,
} from '../api/gameLifecycle'
import type { EventKind } from '../lib/sync/eventKinds'
import type { SyncEvent } from '../lib/sync/syncEvent'
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
import { readOrdinaryPitchAck } from '../api/ordinaryPitchAck'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  isOrdinaryAppendPolicy,
  nextOrdinaryD2,
  type OrdinaryAppendPolicy,
} from '../api/ordinaryAppendPolicy'
import { isStartedGameTimestamp } from '../api/startedGame'
import { canonicalUuid } from '../api/authIntent'
import {
  NativeEnvelopePersistence,
  type StoredNativeEnvelope,
} from '../api/nativeUndoWire'
import { CANON_ACK_STATE_RESULT } from '../lib/sync/canonOracle'
import { parseD1AckEnvelope } from '../lib/sync/ackEnvelope'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'
import {
  runAsSingleWriter,
  singleWriterLockName,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import { applyAckToSlot } from './GameScreenAckApplication'
import { appendPitchEventUnderLock } from './GameScreenPitchAcceptance'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import type { FirstBallIdentity } from './GameScreenFirstBallController'

/** 未確定/未送信の表示に使う上限。超えたら「以上」と表示し、全件走査を装わない。 */
const QUEUE_SCAN_LIMIT = 5000
/** 1回の再送で順に送るlifecycle操作の上限。 */
const RETRY_CHAIN_LIMIT = 16
/** lifecycle payload の識別。queue slot がこのunitの操作かを値から判定する。 */
const LIFECYCLE_PAYLOAD_FORMAT = 'native-game-lifecycle-v1'
/** 送信を1度でも試みたかを残す小さな耐久store。未送信と結果不明を分ける。 */
const DISPATCH_DATABASE = 'pitchlog-game-lifecycle-dispatch'
const DISPATCH_STORE = 'dispatched'
/** 最後に実GETで確認したbase。通信断中の終了/再開の起点にする。 */
const BASE_DATABASE = 'pitchlog-game-lifecycle-base'
const BASE_STORE = 'bases'

type DispatchKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d5: string
}>

function dispatchKey(key: DispatchKey): IDBValidKey {
  return [key.tenantId, key.gameId, key.d4, key.d5] as IDBValidKey
}

function baseKey(
  key: Readonly<{ tenantId: string; gameId: string; d4: string }>,
) {
  return [key.tenantId, key.gameId, key.d4] as IDBValidKey
}

function secureStorage(): boolean {
  return Boolean(globalThis.isSecureContext && globalThis.indexedDB)
}

function openStore(
  databaseName: string,
  storeName: string,
  keyPath: readonly string[],
): Promise<IDBDatabase> {
  if (!secureStorage()) throw new Error('端末の保存領域を利用できません')
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = globalThis.indexedDB.open(databaseName, 1)
    request.onerror = () => reject(new Error('端末の保存領域を開けません'))
    request.onblocked = () => reject(new Error('端末の保存領域を開けません'))
    request.onupgradeneeded = () => {
      request.result.createObjectStore(storeName, { keyPath: [...keyPath] })
    }
    request.onsuccess = () => resolve(request.result)
  })
}

function strictTransaction(
  database: IDBDatabase,
  storeName: string,
  mode: IDBTransactionMode,
  durability: IDBTransactionOptions['durability'],
): IDBTransaction {
  const transaction = database.transaction(storeName, mode, { durability })
  if (durability === 'strict' && transaction.durability !== 'strict') {
    transaction.abort()
    throw new Error('端末への確定を保証できません')
  }
  return transaction
}

/**
 * 送信直前のマーカーだけを持つstore。資格・本文は保持しない。
 *
 * マーカーがあれば「送信を試みた」＝結果不明として表示し、無ければ未送信として
 * 扱う。マーカーは送信前にstrict commitし、送信の成否で消さない。
 */
class LifecycleDispatchPersistence {
  readonly #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(): Promise<LifecycleDispatchPersistence> {
    const database = await openStore(DISPATCH_DATABASE, DISPATCH_STORE, [
      'tenantId',
      'gameId',
      'd4',
      'd5',
    ])
    try {
      const store = database
        .transaction(DISPATCH_STORE, 'readonly')
        .objectStore(DISPATCH_STORE)
      if (
        JSON.stringify(store.keyPath) !==
        JSON.stringify(['tenantId', 'gameId', 'd4', 'd5'])
      )
        throw new Error('送信マーカーの形が違います')
    } catch (error) {
      database.close()
      throw error
    }
    return new LifecycleDispatchPersistence(database)
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#database.close()
  }

  async mark(key: DispatchKey, attemptId: string): Promise<void> {
    if (this.#closed) throw new Error('送信マーカーを保存できません')
    await new Promise<void>((resolve, reject) => {
      const transaction = strictTransaction(
        this.#database,
        DISPATCH_STORE,
        'readwrite',
        'strict',
      )
      transaction.oncomplete = () => resolve()
      transaction.onabort = () =>
        reject(new Error('送信マーカーを確定できません'))
      transaction.onerror = () => {
        // abort が最終結果を通知する。
      }
      const store = transaction.objectStore(DISPATCH_STORE)
      const request = store.get(dispatchKey(key))
      request.onsuccess = () => {
        const existing = request.result as Record<string, unknown> | undefined
        if (existing === undefined)
          store.add({ ...key, attemptId, at: Date.now() })
        else if (existing.attemptId !== attemptId)
          reject(new Error('送信マーカーが一致しません'))
      }
      request.onerror = () => reject(new Error('送信マーカーを読めません'))
    })
  }

  async has(key: DispatchKey): Promise<boolean> {
    if (this.#closed) throw new Error('送信マーカーを読めません')
    return new Promise<boolean>((resolve, reject) => {
      const transaction = this.#database.transaction(DISPATCH_STORE, 'readonly')
      const request = transaction
        .objectStore(DISPATCH_STORE)
        .get(dispatchKey(key))
      request.onsuccess = () => resolve(request.result !== undefined)
      request.onerror = () => reject(new Error('送信マーカーを読めません'))
      transaction.onabort = () => reject(new Error('送信マーカーを読めません'))
    })
  }
}

/** 実GETで確認したbase。書込資格ではなく、依存refとD2採番の起点。 */
export type GameLifecycleBase = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  status: GameLifecycleStatus
  lastVersion: string
  active: GameLifecycleTarget | null
  checkpointRef: Readonly<{ id: string; revision: string; digest: string }>
  /** 実GETのcheckpointが含む最後の受理D1。 */
  d3: string
  /** 実GETのnext_position.d2。本地chainのD2採番の起点。 */
  nextD2: string
  appendPolicy: OrdinaryAppendPolicy
  recoveryGeneration: string
  lastSavedAt: string
}>

function isBase(value: unknown): value is GameLifecycleBase {
  if (typeof value !== 'object' || value === null || Array.isArray(value))
    return false
  const row = value as Record<string, unknown>
  if (
    Object.keys(row).sort().join(',') !==
    'active,appendPolicy,checkpointRef,d3,d4,gameId,lastSavedAt,lastVersion,nextD2,recoveryGeneration,status,tenantId'
  )
    return false
  if (
    typeof row.tenantId !== 'string' ||
    typeof row.gameId !== 'string' ||
    !canonicalUuid.test(row.tenantId) ||
    !canonicalUuid.test(row.gameId) ||
    typeof row.d4 !== 'string' ||
    !/^d4\.1\.[A-Za-z0-9_-]{55}$/.test(row.d4) ||
    (row.status !== 'in_progress' && row.status !== 'finished') ||
    typeof row.lastVersion !== 'string' ||
    !/^(?:0|[1-9][0-9]*)$/.test(row.lastVersion) ||
    typeof row.d3 !== 'string' ||
    !/^(?:0|[1-9][0-9]*)$/.test(row.d3) ||
    typeof row.nextD2 !== 'string' ||
    !/^[1-9][0-9]*$/.test(row.nextD2) ||
    !isOrdinaryAppendPolicy(row.appendPolicy) ||
    typeof row.recoveryGeneration !== 'string' ||
    !/^[1-9][0-9]*$/.test(row.recoveryGeneration) ||
    !isStartedGameTimestamp(row.lastSavedAt)
  )
    return false
  const ref = row.checkpointRef
  if (
    typeof ref !== 'object' ||
    ref === null ||
    Array.isArray(ref) ||
    Object.keys(ref).sort().join(',') !== 'digest,id,revision'
  )
    return false
  const checkpointRef = ref as Record<string, unknown>
  if (
    typeof checkpointRef.id !== 'string' ||
    !canonicalUuid.test(checkpointRef.id) ||
    typeof checkpointRef.revision !== 'string' ||
    !/^[1-9][0-9]*$/.test(checkpointRef.revision) ||
    typeof checkpointRef.digest !== 'string' ||
    !/^[0-9a-f]{64}$/.test(checkpointRef.digest)
  )
    return false
  if (row.active === null) return row.status === 'in_progress'
  if (row.status !== 'finished') return false
  const active = row.active
  if (typeof active !== 'object' || active === null || Array.isArray(active))
    return false
  const target = active as Record<string, unknown>
  return (
    Object.keys(target).sort().join(',') === 'eventId,receiptId,version' &&
    typeof target.version === 'string' &&
    /^[1-9][0-9]*$/.test(target.version) &&
    target.version === row.lastVersion &&
    typeof target.eventId === 'string' &&
    canonicalUuid.test(target.eventId) &&
    typeof target.receiptId === 'string' &&
    canonicalUuid.test(target.receiptId)
  )
}

function baseFromGame(game: GameLifecycleGame): GameLifecycleBase {
  return {
    tenantId: game.checkpoint.content.scope.tenantId,
    gameId: game.id,
    d4: game.current_d4,
    status: game.status,
    lastVersion: game.lifecycle.lastVersion,
    active:
      game.lifecycle.active === null
        ? null
        : {
            version: game.lifecycle.active.version,
            eventId: game.lifecycle.active.eventId,
            receiptId: game.lifecycle.active.receiptId,
          },
    checkpointRef: {
      id: game.checkpoint.ref.id,
      revision: game.checkpoint.ref.revision,
      digest: game.checkpoint.ref.digest,
    },
    d3: game.checkpoint.content.d3,
    nextD2: game.next_position.d2,
    appendPolicy: { ...game.append_policy },
    recoveryGeneration: game.recovery_generation,
    lastSavedAt: game.last_saved_at,
  }
}

/** 最後に実GETで確認したbaseの耐久store。 */
class LifecycleBasePersistence {
  readonly #database: IDBDatabase
  #closed = false

  private constructor(database: IDBDatabase) {
    this.#database = database
    database.onversionchange = () => this.close()
  }

  static async open(): Promise<LifecycleBasePersistence> {
    const database = await openStore(BASE_DATABASE, BASE_STORE, [
      'tenantId',
      'gameId',
      'd4',
    ])
    try {
      const store = database
        .transaction(BASE_STORE, 'readonly')
        .objectStore(BASE_STORE)
      if (
        JSON.stringify(store.keyPath) !==
        JSON.stringify(['tenantId', 'gameId', 'd4'])
      )
        throw new Error('lifecycle baseの形が違います')
    } catch (error) {
      database.close()
      throw error
    }
    return new LifecycleBasePersistence(database)
  }

  close(): void {
    if (this.#closed) return
    this.#closed = true
    this.#database.close()
  }

  async read(key: Readonly<{ tenantId: string; gameId: string; d4: string }>) {
    if (this.#closed) throw new Error('lifecycle baseを読めません')
    return new Promise<GameLifecycleBase | null>((resolve, reject) => {
      const transaction = this.#database.transaction(BASE_STORE, 'readonly')
      const request = transaction.objectStore(BASE_STORE).get(baseKey(key))
      request.onsuccess = () => {
        if (request.result === undefined) resolve(null)
        else if (isBase(request.result)) resolve(request.result)
        else reject(new Error('lifecycle baseが不正です'))
      }
      request.onerror = () => reject(new Error('lifecycle baseを読めません'))
      transaction.onabort = () =>
        reject(new Error('lifecycle baseを読めません'))
    })
  }

  async write(value: GameLifecycleBase): Promise<void> {
    if (this.#closed) throw new Error('lifecycle baseを保存できません')
    if (!isBase(value)) throw new Error('lifecycle baseが不正です')
    await new Promise<void>((resolve, reject) => {
      const transaction = strictTransaction(
        this.#database,
        BASE_STORE,
        'readwrite',
        'strict',
      )
      transaction.oncomplete = () => resolve()
      transaction.onabort = () =>
        reject(new Error('lifecycle baseを確定できません'))
      transaction.onerror = () => {
        // abort が最終結果を通知する。
      }
      transaction.objectStore(BASE_STORE).put(value)
    })
  }
}

export const GAME_LIFECYCLE_REASON = {
  BUSY: 'busy',
  IDENTITY_CHANGED: 'identity-changed',
  STORAGE_UNAVAILABLE: 'storage-unavailable',
  GRANT_UNAVAILABLE: 'grant-unavailable',
  /** 開始grantsのD4/recovery/lineupが実GETと食い違う。 */
  GRANT_CHANGED: 'grant-changed',
  /** 他タブが記録中で、この端末は書き手ではない。 */
  LOCK_UNAVAILABLE: 'lock-unavailable',
  READ_NOT_FOUND: 'read-not-found',
  READ_UNAVAILABLE: 'read-unavailable',
  /** 旧server/旧projection。新縦断の成功にしない。 */
  READ_UNSUPPORTED: 'read-unsupported',
  READ_FAILED: 'read-failed',
  /** 一度も実GETでbaseを確認できていない。 */
  READ_REQUIRED: 'read-required',
  /** 操作の前提status/activeが実GETと食い違う。 */
  STATUS_MISMATCH: 'status-mismatch',
  /** 終了なしに追記再開しようとしている（targetを作れない）。 */
  TARGET_UNAVAILABLE: 'target-unavailable',
  /** 再開種別が正本の写しに無い（root追補待ち）。 */
  REOPEN_KIND_UNAVAILABLE: 'reopen-kind-unavailable',
  /** 同じqueueに先行の未終結slotがある。飛ばさない。 */
  PENDING_PREDECESSOR: 'pending-predecessor',
  /** 同じqueueに先行があるため追記は受理したが送信していない。 */
  QUEUED_AWAITING_PREDECESSOR: 'queued-awaiting-predecessor',
  /** queue受理前の準備行が残っている。 */
  PREPARED_ENVELOPE: 'prepared-envelope',
  /** 別機能の準備行がある。取り違えない。 */
  FOREIGN_PREPARED_ENVELOPE: 'foreign-prepared-envelope',
  /** 追記が成立しなかった。 */
  QUEUE_APPEND_REJECTED: 'queue-append-rejected',
  /** 追記の成否を確かめられない。 */
  QUEUE_APPEND_UNDETERMINED: 'queue-append-undetermined',
  /** 耐久storeへ確定できない。追記しない。 */
  DURABILITY_UNAVAILABLE: 'durability-unavailable',
  /** 受理済みslotと保存本文が食い違う。送らない。 */
  REQUEST_BODY_MISMATCH: 'request-body-mismatch',
  /** 原本文が見つからない。新本文を作らない。 */
  PREPARED_ENVELOPE_UNAVAILABLE: 'prepared-envelope-unavailable',
  /** 送信できなかった/応答を解釈できなかった。保存成功にしない。 */
  SEND_NOT_ACCEPTED: 'send-not-accepted',
  /** ACKが同slotの受理/重複を示さない。 */
  ACK_NOT_APPLIED: 'ack-not-applied',
  /** 要操作slotが残っている。自動再送しない。 */
  REQUIRES_OPERATOR: 'requires-operator',
  /** 終了後に追加操作があるなど、queue chainが順序に反する。 */
  INVALID_ORDER: 'invalid-order',
  /** ローカルのbase/準備行が壊れている。 */
  INVALID_LOCAL_STATE: 'invalid-local-state',
  /** D2の次ラベルを採番できない。 */
  D2_EXHAUSTED: 'd2-exhausted',
  /** ACK後の実GETがACK対象より古い。再取得未了。 */
  STALE_READ: 'stale-read',
  OPERATION_FAILED: 'operation-failed',
  SCAN_TRUNCATED: 'scan-truncated',
} as const

export type GameLifecycleReason =
  (typeof GAME_LIFECYCLE_REASON)[keyof typeof GAME_LIFECYCLE_REASON]

export type GameLifecycleRefreshState = 'idle' | 'done' | 'failed'

export type GameLifecycleAck = 'accepted' | 'duplicate'

export type GameLifecycleHandoff = Readonly<{
  gameId: string
  tenantId: string
  nextPosition: Readonly<{ d1: string; d2: string }>
  checkpointRef: Readonly<{ id: string; revision: string; digest: string }>
  recoveryGeneration: string
  lastSavedAt: string
}>

export type GameLifecycleView = Readonly<{
  /** 実GETのbaseと耐久chainから導いた期待status。 */
  status: GameLifecycleStatus | null
  /** 最後に実GETで確認したstatus。 */
  confirmedStatus: GameLifecycleStatus | null
  lastVersion: string | null
  active: GameLifecycleTarget | null
  lastSavedAt: string | null
  /** 実GETで確認した次の位置。本地の未確定操作は含まない。 */
  nextPosition: Readonly<{ d1: string; d2: string }> | null
  recoveryGeneration: string | null
  checkpointRef: Readonly<{
    id: string
    revision: string
    digest: string
  }> | null
  pageItemCount: number
  hasNextPage: boolean
  /** 未送信のlifecycle操作（送信をまだ試みていない）。 */
  preparedCount: number
  /** 送信を試みたが受理を確認できていないlifecycle操作。 */
  unknownCount: number
  /** 送信本文を復元できないlifecycle操作。 */
  unpreparedCount: number
  /** 上記のlifecycle未確認の合計。 */
  pendingLifecycleCount: number
  /** 他の操作の未終結slot。 */
  otherUnsettledCount: number
  scanTruncated: boolean
  saveAck: GameLifecycleAck | null
  refresh: GameLifecycleRefreshState
  /** 実GETが失敗またはACK対象より古く、表示が確認済みでない。 */
  stale: boolean
  lastFailure: GameLifecycleReason | null
  /** 現在のbase/chainで操作を開始できない理由。 */
  blockedReason: GameLifecycleReason | null
  reopenBlocked: boolean
  canEnd: boolean
  canReopen: boolean
  canRetry: boolean
  busy: boolean
  resumeHandoff: GameLifecycleHandoff | null
}>

export type GameLifecycleOperationResult =
  | Readonly<{ outcome: 'blocked'; reason: GameLifecycleReason }>
  | Readonly<{
      outcome: 'pending'
      reason: GameLifecycleReason
      status?: number
    }>
  | Readonly<{
      outcome: 'acked'
      ack: GameLifecycleAck | null
      refresh: 'done' | 'pending'
    }>

type Resources = Readonly<{
  queue: DurableQueue
  envelopes: NativeEnvelopePersistence
  dispatches: LifecycleDispatchPersistence
  bases: LifecycleBasePersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}>

type LifecycleSlot = Readonly<{
  slot: DurableQueueSlot
  action: GameLifecycleAction
  body: GameLifecycleRequestBody
  eventId: string
  receiptId: string
  dispatched: boolean
}>

type Snapshot = Readonly<{
  nextD1: number
  lastSlot: DurableQueueSlot | null
  oldestUnsettled: DurableQueueSlot | null
  lastLifecycle: LifecycleSlot | null
  lifecycle: readonly LifecycleSlot[]
  /** 同一game/D4の全slot。prefix連続性の確認に使う。 */
  byD1: ReadonlyMap<number, DurableQueueSlot>
  preparedCount: number
  unknownCount: number
  unpreparedCount: number
  otherUnsettledCount: number
  rejectedLifecycle: boolean
  truncated: boolean
  preparedOrphan: StoredNativeEnvelope | null
  foreignPrepared: boolean
  effectiveStatus: GameLifecycleStatus | null
  invalidOrder: boolean
  broken: boolean
}>

type Precondition =
  Readonly<{ ok: true }> | Readonly<{ ok: false; reason: GameLifecycleReason }>

type Selection<Value> =
  | Readonly<{ ok: true; value: Value }>
  | Readonly<{ ok: false; reason: GameLifecycleReason }>

type InternalOperationResult =
  | Readonly<{ kind: 'blocked'; reason: GameLifecycleReason }>
  | Readonly<{
      kind: 'pending'
      reason: GameLifecycleReason
      status?: number
    }>
  | Readonly<{
      kind: 'acked'
      ack: GameLifecycleAck | null
      d1: number
    }>

/**
 * 実記録画面の単一書き手前提を、既存の環境確認から組み立てる。
 *
 * 常時trueを作らない。hostは既存のHTTPS表示・ブラウザプロファイル・閲覧モード・
 * storage bucket・Lockdown・認証の確認結果をgetterで渡す。
 */
export type GameLifecycleWriterEnvironment = Readonly<{
  topLevelHttps: () => boolean
  sameBrowserProfile: () => boolean
  sameBrowsingMode: () => boolean
  sameStorageBucket: () => boolean
  siteStorageAvailable: () => boolean
  lockdownModeNotApplied: () => boolean
  identityVerified: () => boolean
}>

export function createGameLifecycleWriter(
  environment: GameLifecycleWriterEnvironment,
): SingleWriterInjections {
  return {
    resolvePreconditions: () => ({
      topLevelHttps: environment.topLevelHttps(),
      sameBrowserProfile: environment.sameBrowserProfile(),
      sameBrowsingMode: environment.sameBrowsingMode(),
      sameStorageBucket: environment.sameStorageBucket(),
      siteStorageAvailable: environment.siteStorageAvailable(),
      lockdownModeNotApplied: environment.lockdownModeNotApplied(),
    }),
    revalidateSingleWriter: () =>
      environment.identityVerified() &&
      environment.topLevelHttps() &&
      environment.sameBrowserProfile() &&
      environment.sameBrowsingMode() &&
      environment.sameStorageBucket() &&
      environment.lockdownModeNotApplied(),
  }
}

export type GameLifecycleControllerOptions = Readonly<{
  /** 実記録画面の単一書き手前提。省略すると操作できない（常時trueの既定を作らない）。 */
  writer: SingleWriterInjections
  /**
   * 正本の写しが未裁定の間の順序検査だけに使う。
   * 製品配線は渡さない（未裁定種別をcastで通さない）。
   */
  resolveEventKind?: (action: GameLifecycleAction) => EventKind | undefined
}>

function isLifecycleEvent(event: SyncEvent): boolean {
  const payload = event.fields.V7
  return (
    typeof payload === 'object' &&
    payload !== null &&
    !Array.isArray(payload) &&
    (payload as Record<string, unknown>).formatVersion ===
      LIFECYCLE_PAYLOAD_FORMAT
  )
}

function isLifecycleSlot(slot: DurableQueueSlot): boolean {
  return isLifecycleEvent(slot.event)
}

function isUnsettled(slot: DurableQueueSlot): boolean {
  return (
    slot.state === queueStateId('未送信') ||
    slot.state === queueStateId('要操作')
  )
}

function ackKind(value: unknown): GameLifecycleAck | null {
  try {
    const envelope = parseD1AckEnvelope(value)
    const [result] = envelope.eventResults
    if (result?.a5Result.id === CANON_ACK_STATE_RESULT.ACCEPTED)
      return 'accepted'
    if (result?.a5Result.id === CANON_ACK_STATE_RESULT.DUPLICATE)
      return 'duplicate'
    return null
  } catch {
    return null
  }
}

function actionOf(body: GameLifecycleRequestBody): GameLifecycleAction | null {
  const kind = body.events[0]?.event_kind
  if (kind === 'game_end_declaration') return 'end'
  if (kind === 'game_reopen') return 'reopen'
  return null
}

function publicResult(
  result: InternalOperationResult,
): GameLifecycleOperationResult {
  if (result.kind === 'acked')
    return { outcome: 'acked', ack: result.ack, refresh: 'done' }
  if (result.kind === 'pending')
    return {
      outcome: 'pending',
      reason: result.reason,
      ...(result.status === undefined ? {} : { status: result.status }),
    }
  return { outcome: 'blocked', reason: result.reason }
}

function safeInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : null
}

/** 終了/追記再開を、既queue・実排他・既ACK・実GETへ接続する。 */
export class GameLifecycleController {
  readonly #gameId: string
  readonly #readIdentity: () => FirstBallIdentity
  #identity: FirstBallIdentity
  readonly #writer: SingleWriterInjections
  readonly #resolveEventKind: (
    action: GameLifecycleAction,
  ) => EventKind | undefined
  #resources: Resources | null = null
  #opening: Promise<void> | null = null
  #base: GameLifecycleBase | null = null
  #game: GameLifecycleGame | null = null
  #scan: Snapshot | null = null
  #saveAck: GameLifecycleAck | null = null
  #refresh: GameLifecycleRefreshState = 'idle'
  #failure: GameLifecycleReason | null = null
  #busy = false
  #disposed = false

  constructor(
    gameId: string,
    readIdentity: () => FirstBallIdentity,
    options: GameLifecycleControllerOptions,
  ) {
    this.#gameId = gameId
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
    this.#writer = options.writer
    this.#resolveEventKind = options.resolveEventKind ?? gameLifecycleEventKind
  }

  #assert(): void {
    const now = this.#readIdentity()
    if (
      this.#disposed ||
      !now.verified ||
      !this.#identity.verified ||
      now.tenantId === null ||
      now.tenantId !== this.#identity.tenantId ||
      now.epoch !== this.#identity.epoch
    )
      throw new Error('終了再開の操作前提を確認できません')
  }

  #current(): boolean {
    try {
      this.#assert()
      return true
    } catch {
      return false
    }
  }

  #scope(): { game: string; d4: string } {
    const r = this.#resources
    if (!r) throw new Error('記録資源が未接続です')
    return { game: this.#gameId, d4: r.grant.d4 }
  }

  async #open(): Promise<void> {
    this.#assert()
    if (this.#resources) return
    if (this.#opening) return this.#opening
    this.#opening = (async () => {
      let store: GameStartPersistence | null = null
      let queue: DurableQueue | null = null
      let envelopes: NativeEnvelopePersistence | null = null
      let dispatches: LifecycleDispatchPersistence | null = null
      let bases: LifecycleBasePersistence | null = null
      try {
        store = await GameStartPersistence.open()
        const tenant = this.#identity.tenantId!
        const device = await store.readDevice(tenant)
        const start = await store.readStart(tenant, this.#gameId)
        this.#assert()
        if (!device || !start || start.status !== 'received' || !start.grant)
          throw new Error('端末の開始資格がありません')
        if (device.device_id !== start.grant.device_id)
          throw new Error('端末と開始資格が一致しません')
        queue = await openDurableQueue({
          databaseName: 'pitchlog-first-ball-queue-' + tenant,
        })
        envelopes = await NativeEnvelopePersistence.open()
        dispatches = await LifecycleDispatchPersistence.open()
        bases = await LifecycleBasePersistence.open()
        this.#assert()
        this.#resources = {
          queue,
          envelopes,
          dispatches,
          bases,
          device,
          grant: start.grant,
        }
        if (!this.#base) {
          this.#base = await bases.read({
            tenantId: tenant,
            gameId: this.#gameId,
            d4: start.grant.d4,
          })
        }
        queue = null
        envelopes = null
        dispatches = null
        bases = null
      } catch (error) {
        // base読取失敗で閉じる資源を、次の再試行に再利用させない。
        this.#resources = null
        throw error
      } finally {
        store?.close()
        queue?.close()
        envelopes?.close()
        dispatches?.close()
        bases?.close()
      }
    })()
    try {
      await this.#opening
    } finally {
      this.#opening = null
    }
  }

  /** 実GETを1回だけ行い、tenant/grantsとの一致を確認する。 */
  async #readFresh(): Promise<
    | Readonly<{ ok: true; game: GameLifecycleGame }>
    | Readonly<{ ok: false; reason: GameLifecycleReason }>
  > {
    let result
    try {
      result = await readGameLifecycle(this.#gameId, { limit: 25 })
    } catch {
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_FAILED }
    }
    if (result.kind === 'not-found')
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_NOT_FOUND }
    if (result.kind === 'unavailable')
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_UNAVAILABLE }
    if (result.kind === 'unsupported')
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_UNSUPPORTED }
    this.#assert()
    const game = result.game
    const r = this.#resources
    if (!r)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
    if (
      game.id !== this.#gameId ||
      game.checkpoint.content.scope.tenantId !== this.#identity.tenantId
    )
      return { ok: false, reason: GAME_LIFECYCLE_REASON.IDENTITY_CHANGED }
    if (
      game.current_d4 !== r.grant.d4 ||
      game.recovery_generation !== r.grant.recovery_generation ||
      game.lineups.away.lineup_id !== r.grant.away_lineup_id ||
      game.lineups.home.lineup_id !== r.grant.home_lineup_id
    )
      return { ok: false, reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED }
    const base = baseFromGame(game)
    if (!isBase(base))
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_FAILED }
    return { ok: true, game }
  }

  async #adopt(game: GameLifecycleGame): Promise<void> {
    const base = baseFromGame(game)
    if (!isBase(base)) throw new Error('lifecycle baseを形成できません')
    await this.#resources!.bases.write(base)
    this.#game = game
    this.#base = base
  }

  /**
   * 実GETでbaseを更新する。ACK後は期待状態を照合し、古いGETを採用しない。
   *
   * Args:
   *     expected: 直前ACK対象。省略しても耐久queueのACK到達下限を毎回検査する。
   */
  async #refreshInternal(
    expected?: Readonly<{
      action: GameLifecycleAction
      minimumD1: number
      expectedStatus: GameLifecycleStatus
      expectedLastVersion: string
      expectedTarget: GameLifecycleTarget | null
    }>,
  ): Promise<boolean> {
    const fresh = await this.#readFresh()
    if (!fresh.ok) {
      this.#refresh = 'failed'
      this.#failure = fresh.reason
      return false
    }
    // 確定版は単調。古い/食い違うGETを新しいbaseとして採用しない。
    const known = this.#base
    if (known) {
      const nextVersion = BigInt(fresh.game.lifecycle.lastVersion)
      const knownVersion = BigInt(known.lastVersion)
      if (
        nextVersion < knownVersion ||
        BigInt(fresh.game.checkpoint.content.d3) < BigInt(known.d3)
      ) {
        this.#refresh = 'failed'
        this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
        return false
      }
      if (
        nextVersion === knownVersion &&
        known.status === 'finished' &&
        fresh.game.status === 'finished' &&
        known.active !== null &&
        fresh.game.lifecycle.active !== null &&
        (known.active.eventId !== fresh.game.lifecycle.active.eventId ||
          known.active.receiptId !== fresh.game.lifecycle.active.receiptId)
      ) {
        this.#refresh = 'failed'
        this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
        return false
      }
    }
    // ACKはqueueの同期済みslotへ耐久適用される。メモリ上の直前操作に依存せず、
    // 手動refresh/retry/reloadでも同じ下限を復元してからGETを採用する。
    {
      try {
        // baseだけ失われたreloadでも、GETを仮の基点としてqueueのACKを先に確認する。
        // 仮基点はまだ保存・採用せず、失われたbaseの内容を推測で補わない。
        const floorBase = known ?? baseFromGame(fresh.game)
        const snapshot = await this.#snapshot(floorBase)
        if (snapshot.truncated || snapshot.broken)
          throw new Error('ACK済み到達下限を確認できません')
        const acknowledged = snapshot.lifecycle.filter(
          ({ slot }) => slot.state === queueStateId('同期済み'),
        )
        const last = acknowledged.at(-1)
        const d3 = BigInt(fresh.game.checkpoint.content.d3)
        if (
          last &&
          (d3 < BigInt(last.slot.d1) ||
            (d3 === BigInt(last.slot.d1) &&
              (fresh.game.status !==
                (last.action === 'end' ? 'finished' : 'in_progress') ||
                (last.action === 'end' &&
                  (fresh.game.lifecycle.active?.eventId !== last.eventId ||
                    fresh.game.lifecycle.active.receiptId !==
                      last.receiptId)))))
        ) {
          this.#refresh = 'failed'
          this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
          return false
        }
        if (last) {
          const version = this.#acknowledgedVersionFloor(snapshot, last)
          if (!version.ok && !known) {
            this.#refresh = 'failed'
            this.#failure = GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
            return false
          }
          if (
            version.ok &&
            !matchesExpected(fresh.game, {
              action: last.action,
              minimumD1: last.slot.d1,
              expectedStatus:
                last.action === 'end' ? 'finished' : 'in_progress',
              expectedLastVersion: version.value,
              expectedTarget:
                last.action === 'end'
                  ? {
                      version: version.value,
                      eventId: last.eventId,
                      receiptId: last.receiptId,
                    }
                  : null,
            })
          ) {
            this.#refresh = 'failed'
            this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
            return false
          }
        }
        if (last && BigInt(last.slot.d1) > BigInt(floorBase.d3)) {
          for (const slot of snapshot.byD1.values()) {
            if (
              BigInt(slot.d1) > BigInt(floorBase.d3) &&
              slot.d1 <= last.slot.d1 &&
              slot.state !== queueStateId('同期済み')
            )
              throw new Error('先行要求のACKが未確認です')
          }
          const floor = this.#expectedAfter(floorBase, snapshot, last.slot.d1)
          if (
            !floor.ok ||
            !matchesExpected(fresh.game, {
              action: last.action,
              minimumD1: last.slot.d1,
              ...floor.value,
            })
          ) {
            this.#refresh = 'failed'
            this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
            return false
          }
        }
      } catch {
        this.#refresh = 'failed'
        this.#failure = GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
        return false
      }
    }
    if (expected && !matchesExpected(fresh.game, expected)) {
      // ACKは成立しているが、表示はまだACK対象を反映していない。
      this.#refresh = 'failed'
      this.#failure = GAME_LIFECYCLE_REASON.STALE_READ
      return false
    }
    try {
      await this.#adopt(fresh.game)
    } catch {
      this.#refresh = 'failed'
      this.#failure = GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
      return false
    }
    this.#refresh = 'done'
    this.#failure = null
    return true
  }

  /** 耐久queueの有限pageだけを読み、baseとchainから期待状態を導く。 */
  async #snapshot(base: GameLifecycleBase): Promise<Snapshot> {
    const r = this.#resources!
    const scope = this.#scope()
    const slots: DurableQueueSlot[] = []
    let cursor: number | null = null
    let truncated = false
    do {
      const page = await r.queue.readSlotsPage(scope, cursor, 100)
      for (const slot of page.items) {
        slots.push(slot)
        if (slots.length > QUEUE_SCAN_LIMIT) {
          truncated = true
          break
        }
      }
      if (truncated) break
      cursor = page.nextCursorD1
    } while (cursor !== null)

    const nextD1 = await r.queue.readNextD1(scope)
    if (!Number.isSafeInteger(nextD1) || nextD1 < 1)
      throw new Error('次のD1を確認できません')
    const byD1 = new Map<number, DurableQueueSlot>()
    for (const slot of slots) byD1.set(slot.d1, slot)

    let oldestUnsettled: DurableQueueSlot | null = null
    let otherUnsettledCount = 0
    for (const slot of slots) {
      if (!isUnsettled(slot)) continue
      if (!oldestUnsettled) oldestUnsettled = slot
      if (!isLifecycleSlot(slot)) otherUnsettledCount += 1
    }

    const d3 = BigInt(base.d3)
    const lifecycle: LifecycleSlot[] = []
    let broken = false
    let rejectedLifecycle = false
    let preparedCount = 0
    let unknownCount = 0
    let unpreparedCount = 0
    for (const slot of slots) {
      if (
        BigInt(slot.d1) <= d3 &&
        isUnsettled(slot) &&
        !isLifecycleSlot(slot)
      ) {
        // 実GETは受理済みと言うD1が、通常操作の未終結slotとして残っている。
        // 既入力側の再送で解消されるまでlifecycleの前提を作らない。
        broken = true
      }
      if (!isLifecycleSlot(slot)) continue
      let stored: StoredNativeEnvelope | null = null
      try {
        stored = await r.envelopes.read({
          tenantId: this.#identity.tenantId!,
          gameId: this.#gameId,
          d4: r.grant.d4,
          d1: slot.d1,
          d5: String(slot.d5),
        })
      } catch {
        stored = null
      }
      let body: GameLifecycleRequestBody | null = null
      try {
        const parsed: unknown = stored ? JSON.parse(stored.requestJson) : null
        if (isGameLifecycleRequestBody(parsed)) body = parsed
      } catch {
        body = null
      }
      const action = body ? actionOf(body) : null
      if (!stored || !body || action === null) {
        broken = true
        if (BigInt(slot.d1) > d3 || slot.state === queueStateId('未送信'))
          unpreparedCount += 1
        continue
      }
      const payload = body.events[0]?.payload as
        Record<string, unknown> | undefined
      const event = payload?.event as Record<string, unknown> | undefined
      if (
        !event ||
        typeof event.eventId !== 'string' ||
        typeof event.receiptId !== 'string' ||
        !sameOrdinaryWire(payload, slot.event.fields.V7) ||
        body.events[0]?.d1 !== slot.d1 ||
        body.events[0]?.d4 !== slot.d4 ||
        body.events[0]?.d5 !== slot.d5 ||
        body.events[0]?.game_id !== this.#gameId
      ) {
        broken = true
        continue
      }
      let dispatched = false
      try {
        dispatched = await r.dispatches.has({
          tenantId: this.#identity.tenantId!,
          gameId: this.#gameId,
          d4: r.grant.d4,
          d5: String(slot.d5),
        })
      } catch {
        broken = true
      }
      lifecycle.push({
        slot,
        action,
        body,
        eventId: event.eventId,
        receiptId: event.receiptId,
        dispatched,
      })
      if (BigInt(slot.d1) <= d3) {
        if (
          slot.state === queueStateId('要操作') ||
          slot.state === queueStateId('退避済み')
        ) {
          rejectedLifecycle = true
          continue
        }
        if (slot.state === queueStateId('未送信')) {
          // 実GETは受理済みと言うが端末のACK適用が済んでいない。送信を試みた
          // 要求なら再送で重複ACKを得て解消できる。準備だけならD1が食い違う。
          if (dispatched) unknownCount += 1
          else broken = true
        }
        continue
      }
      if (
        slot.state === queueStateId('要操作') ||
        slot.state === queueStateId('退避済み')
      ) {
        rejectedLifecycle = true
        continue
      }
      if (slot.state === queueStateId('未送信')) {
        if (dispatched) unknownCount += 1
        else preparedCount += 1
      }
    }
    lifecycle.sort((a, b) => a.slot.d1 - b.slot.d1)

    // baseのstatusに、base以降のlifecycle操作だけをD1順で適用する。
    let effectiveStatus: GameLifecycleStatus | null = base.status
    let invalidOrder = false
    for (const slot of slots) {
      if (BigInt(slot.d1) <= d3) continue
      if (!isLifecycleSlot(slot)) {
        if (effectiveStatus === 'finished') invalidOrder = true
        continue
      }
      const entry = lifecycle.find((value) => value.slot.d1 === slot.d1)
      if (!entry) continue
      if (
        slot.state === queueStateId('未送信') ||
        slot.state === queueStateId('同期済み')
      )
        effectiveStatus = entry.action === 'end' ? 'finished' : 'in_progress'
    }

    let preparedOrphan: StoredNativeEnvelope | null = null
    let foreignPrepared = false
    if (!oldestUnsettled) {
      const occupied = byD1.get(nextD1)
      if (!occupied) {
        const candidate = await r.envelopes.readPreparedSlot({
          tenantId: this.#identity.tenantId!,
          gameId: this.#gameId,
          d4: r.grant.d4,
          d1: nextD1,
        })
        if (candidate) {
          if (isLifecycleEvent(candidate.event)) preparedOrphan = candidate
          else foreignPrepared = true
        }
      }
    }

    return {
      nextD1,
      lastSlot: byD1.get(nextD1 - 1) ?? null,
      oldestUnsettled,
      lastLifecycle:
        lifecycle.length > 0 ? lifecycle[lifecycle.length - 1]! : null,
      lifecycle,
      byD1,
      preparedCount,
      unknownCount,
      unpreparedCount,
      otherUnsettledCount,
      rejectedLifecycle,
      truncated,
      preparedOrphan,
      foreignPrepared,
      effectiveStatus,
      invalidOrder,
      broken,
    }
  }

  #precondition(action: GameLifecycleAction, snapshot: Snapshot): Precondition {
    if (snapshot.broken)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE }
    if (snapshot.rejectedLifecycle)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR }
    if (snapshot.invalidOrder)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_ORDER }
    if (snapshot.effectiveStatus === null)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.READ_REQUIRED }
    if (action === 'end') {
      if (snapshot.effectiveStatus !== 'in_progress')
        return { ok: false, reason: GAME_LIFECYCLE_REASON.STATUS_MISMATCH }
    } else {
      if (snapshot.effectiveStatus !== 'finished')
        return { ok: false, reason: GAME_LIFECYCLE_REASON.TARGET_UNAVAILABLE }
    }
    return { ok: true }
  }

  /** 直前の耐久slotを基点に、閉unionのcheckpointRefを選ぶ。 */
  #checkpointRef(
    snapshot: Snapshot,
    base: GameLifecycleBase,
  ): Selection<GameLifecycleCheckpointRef> {
    const confirmed: GameLifecycleCheckpointRef = {
      kind: 'confirmed',
      id: base.checkpointRef.id,
      revision: base.checkpointRef.revision,
      digest: base.checkpointRef.digest,
    }
    const previous = snapshot.lastSlot
    if (!previous) return { ok: true, value: confirmed }
    const d3 = BigInt(base.d3)
    if (BigInt(previous.d1) <= d3) return { ok: true, value: confirmed }
    if (typeof previous.d5 !== 'string' || !canonicalUuid.test(previous.d5))
      return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE }
    if (previous.state === queueStateId('同期済み')) {
      for (let d1 = Number(d3) + 1; d1 <= previous.d1; d1 += 1) {
        const slot = snapshot.byD1.get(d1)
        if (!slot || slot.state !== queueStateId('同期済み'))
          return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_ORDER }
      }
      return {
        ok: true,
        value: {
          kind: 'confirmed_prefix',
          id: base.checkpointRef.id,
          revision: base.checkpointRef.revision,
          digest: base.checkpointRef.digest,
          d4: base.d4,
          d1: String(previous.d1),
          d5: previous.d5,
        },
      }
    }
    if (previous.state === queueStateId('未送信')) {
      return {
        ok: true,
        value: {
          kind: 'queued_predecessor',
          d4: base.d4,
          d1: String(previous.d1),
          d5: previous.d5,
        },
      }
    }
    return { ok: false, reason: GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR }
  }

  /** 直前の終了版を基点に、閉unionのreopen targetを選ぶ。 */
  #reopenTarget(
    snapshot: Snapshot,
    base: GameLifecycleBase,
  ): Selection<GameLifecycleReopenTarget> {
    const end = snapshot.lastLifecycle
    if (end === null || BigInt(end.slot.d1) <= BigInt(base.d3)) {
      // 端末に終了slotが無い/古い場合でも、サーバー確定済みの最新activeがあれば
      // その版を対象にする（別端末で終了した試合の再開）。
      if (base.active === null)
        return { ok: false, reason: GAME_LIFECYCLE_REASON.TARGET_UNAVAILABLE }
      return {
        ok: true,
        value: {
          kind: 'confirmed',
          version: base.active.version,
          eventId: base.active.eventId,
          receiptId: base.active.receiptId,
        },
      }
    }
    if (end.action !== 'end')
      return { ok: false, reason: GAME_LIFECYCLE_REASON.TARGET_UNAVAILABLE }
    const confirmedActive = base.active
    if (
      confirmedActive !== null &&
      confirmedActive.eventId === end.eventId &&
      confirmedActive.receiptId === end.receiptId
    )
      return {
        ok: true,
        value: {
          kind: 'confirmed',
          version: confirmedActive.version,
          eventId: confirmedActive.eventId,
          receiptId: confirmedActive.receiptId,
        },
      }
    if (typeof end.slot.d5 !== 'string' || !canonicalUuid.test(end.slot.d5))
      return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE }
    return {
      ok: true,
      value: {
        kind: 'queued_end',
        d4: base.d4,
        d1: String(end.slot.d1),
        d5: end.slot.d5,
        eventId: end.eventId,
        receiptId: end.receiptId,
      },
    }
  }

  /** 直前slotのV6又はbaseのnextD2から、共通allocatorで次D2を採番する。 */
  #nextD2(snapshot: Snapshot, base: GameLifecycleBase): Selection<number> {
    if (!snapshot.lastSlot) {
      const value = Number(base.nextD2)
      if (!Number.isSafeInteger(value) || value < 1)
        return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE }
      return { ok: true, value }
    }
    const previous = safeInteger(snapshot.lastSlot.event.fields.V6)
    if (previous === null || previous < 1)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE }
    const next = nextOrdinaryD2(String(previous), base.appendPolicy)
    if (next === null)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.D2_EXHAUSTED }
    const value = Number(next)
    if (!Number.isSafeInteger(value))
      return { ok: false, reason: GAME_LIFECYCLE_REASON.D2_EXHAUSTED }
    return { ok: true, value }
  }

  /** base欠落時も、同期済み要求の確定targetから得た版だけを下限にする。 */
  #acknowledgedVersionFloor(
    snapshot: Snapshot,
    last: LifecycleSlot,
  ): Selection<string> {
    const acknowledged = snapshot.lifecycle.filter(
      (entry) =>
        entry.slot.d1 <= last.slot.d1 &&
        entry.slot.state === queueStateId('同期済み'),
    )
    const targetOf = (entry: LifecycleSlot): GameLifecycleReopenTarget | null =>
      (
        entry.body.events[0]?.payload as Readonly<{
          target: GameLifecycleReopenTarget | null
        }>
      ).target
    let anchorIndex = -1
    for (let index = 0; index < acknowledged.length; index += 1) {
      const entry = acknowledged[index]!
      if (entry.action === 'reopen' && targetOf(entry)?.kind === 'confirmed')
        anchorIndex = index
    }
    if (anchorIndex < 0) {
      // end/queued_endは版を持たない。初期版を終了回数から仮定しない。
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
    }
    const anchor = acknowledged[anchorIndex]!
    const target = targetOf(anchor)
    if (target?.kind !== 'confirmed')
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
    if (last.slot.d1 - anchor.slot.d1 > QUEUE_SCAN_LIMIT)
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
    let version = BigInt(target.version)
    let precedingEnd: LifecycleSlot | null = null
    const acknowledgedByD1 = new Map(
      acknowledged.map((entry) => [entry.slot.d1, entry]),
    )
    for (let d1 = anchor.slot.d1 + 1; d1 <= last.slot.d1; d1 += 1) {
      const slot = snapshot.byD1.get(d1)
      if (!slot || slot.state !== queueStateId('同期済み'))
        return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
      const entry = acknowledgedByD1.get(d1)
      if (!entry) continue
      if (entry.action === 'end') {
        version += 1n
        precedingEnd = entry
        continue
      }
      const queued = targetOf(entry)
      if (
        queued?.kind !== 'queued_end' ||
        precedingEnd === null ||
        queued.d4 !== precedingEnd.slot.d4 ||
        queued.d1 !== String(precedingEnd.slot.d1) ||
        queued.d5 !== precedingEnd.slot.d5 ||
        queued.eventId !== precedingEnd.eventId ||
        queued.receiptId !== precedingEnd.receiptId
      )
        return { ok: false, reason: GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE }
      precedingEnd = null
    }
    return { ok: true, value: version.toString() }
  }

  /** 実GETのstatus/activeが、ACK対象の確定版またはそれ以後かを判定する。 */
  #expectedAfter(
    base: GameLifecycleBase,
    snapshot: Snapshot,
    sentD1: number,
  ): Selection<{
    expectedStatus: GameLifecycleStatus
    expectedLastVersion: string
    expectedTarget: GameLifecycleTarget | null
  }> {
    let status = base.status
    let version = BigInt(base.lastVersion)
    let lastEnd: LifecycleSlot | null = null
    const d3 = BigInt(base.d3)
    for (const entry of snapshot.lifecycle) {
      if (BigInt(entry.slot.d1) <= d3) continue
      if (entry.slot.d1 > sentD1) break
      const state = entry.slot.state
      if (
        state !== queueStateId('未送信') &&
        state !== queueStateId('同期済み')
      )
        continue
      if (entry.action === 'end') {
        version += 1n
        lastEnd = entry
        status = 'finished'
      } else {
        status = 'in_progress'
      }
    }
    if (status === 'finished') {
      if (lastEnd === null) {
        if (base.active === null)
          return {
            ok: false,
            reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE,
          }
        return {
          ok: true,
          value: {
            expectedStatus: 'finished',
            expectedLastVersion: version.toString(),
            expectedTarget: {
              version: base.active.version,
              eventId: base.active.eventId,
              receiptId: base.active.receiptId,
            },
          },
        }
      }
      return {
        ok: true,
        value: {
          expectedStatus: 'finished',
          expectedLastVersion: version.toString(),
          expectedTarget: {
            version: version.toString(),
            eventId: lastEnd.eventId,
            receiptId: lastEnd.receiptId,
          },
        },
      }
    }
    return {
      ok: true,
      value: {
        expectedStatus: 'in_progress',
        expectedLastVersion: version.toString(),
        expectedTarget: null,
      },
    }
  }

  get view(): GameLifecycleView {
    const base = this.#base
    const scan = this.#scan
    const game = this.#game
    const endKind = this.#resolveEventKind('end')
    const reopenKind = this.#resolveEventKind('reopen')
    const pendingLifecycleCount =
      (scan?.preparedCount ?? 0) +
      (scan?.unknownCount ?? 0) +
      (scan?.unpreparedCount ?? 0)
    const unavailable = scan === null || scan.truncated
    const blockedReason = this.#blockedReason(scan)
    const resumeHandoff: GameLifecycleHandoff | null =
      game !== null &&
      base !== null &&
      scan !== null &&
      scan.effectiveStatus === 'in_progress' &&
      pendingLifecycleCount === 0 &&
      !unavailable &&
      !this.#busy &&
      this.#refresh === 'done' &&
      BigInt(game.next_position.d1) === BigInt(scan.nextD1)
        ? {
            gameId: game.id,
            tenantId: base.tenantId,
            nextPosition: { ...game.next_position },
            checkpointRef: { ...base.checkpointRef },
            recoveryGeneration: base.recoveryGeneration,
            lastSavedAt: base.lastSavedAt,
          }
        : null
    return {
      status: scan?.effectiveStatus ?? base?.status ?? null,
      confirmedStatus: base?.status ?? null,
      lastVersion: base?.lastVersion ?? null,
      active: base?.active ?? null,
      lastSavedAt: base?.lastSavedAt ?? null,
      nextPosition:
        base === null
          ? null
          : { d1: (BigInt(base.d3) + 1n).toString(), d2: base.nextD2 },
      recoveryGeneration: base?.recoveryGeneration ?? null,
      checkpointRef: base ? { ...base.checkpointRef } : null,
      pageItemCount: game?.page.items.length ?? 0,
      hasNextPage: game !== null && game.page.next_cursor !== null,
      preparedCount: scan?.preparedCount ?? 0,
      unknownCount: scan?.unknownCount ?? 0,
      unpreparedCount: scan?.unpreparedCount ?? 0,
      pendingLifecycleCount,
      otherUnsettledCount: scan?.otherUnsettledCount ?? 0,
      scanTruncated: scan?.truncated ?? false,
      saveAck: this.#saveAck,
      refresh: this.#refresh,
      stale: this.#refresh !== 'done',
      lastFailure: this.#failure,
      blockedReason,
      reopenBlocked: reopenKind === undefined,
      canEnd:
        scan !== null &&
        !this.#busy &&
        endKind !== undefined &&
        blockedReason === null &&
        scan.effectiveStatus === 'in_progress',
      canReopen:
        scan !== null &&
        !this.#busy &&
        reopenKind !== undefined &&
        blockedReason === null &&
        scan.effectiveStatus === 'finished',
      canRetry:
        !this.#busy &&
        scan !== null &&
        ((scan.oldestUnsettled !== null &&
          isLifecycleSlot(scan.oldestUnsettled)) ||
          scan.preparedOrphan !== null),
      busy: this.#busy,
      resumeHandoff,
    }
  }

  #blockedReason(scan: Snapshot | null): GameLifecycleReason | null {
    if (this.#base === null)
      return this.#failure ?? GAME_LIFECYCLE_REASON.READ_REQUIRED
    if (scan === null) return GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
    if (scan.truncated) return GAME_LIFECYCLE_REASON.SCAN_TRUNCATED
    if (scan.broken) return GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE
    if (scan.rejectedLifecycle) return GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR
    if (scan.invalidOrder) return GAME_LIFECYCLE_REASON.INVALID_ORDER
    if (scan.effectiveStatus === null)
      return GAME_LIFECYCLE_REASON.READ_REQUIRED
    return null
  }

  /** 実GETと耐久queueから表示を復元する。GET不能でもbaseがあれば表示を保つ。 */
  async refresh(): Promise<GameLifecycleView> {
    if (this.#busy) return this.view
    this.#busy = true
    try {
      await this.#open()
      const refreshed = await this.#refreshInternal()
      if (this.#base) {
        try {
          this.#scan = await this.#snapshot(this.#base)
        } catch {
          this.#scan = null
          if (refreshed) {
            this.#refresh = 'failed'
            this.#failure = GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
          }
        }
      }
    } catch {
      this.#refresh = 'failed'
      this.#failure = this.#current()
        ? GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
        : GAME_LIFECYCLE_REASON.IDENTITY_CHANGED
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
    return this.view
  }

  #injections(): SingleWriterInjections {
    const original = this.#writer
    return withNonBlockingSingleWriter({
      ...original,
      revalidateSingleWriter: async (context) => {
        this.#assert()
        return (
          context.gameIdentifier === this.#gameId &&
          context.lockName === singleWriterLockName(this.#gameId) &&
          context.lock !== null &&
          typeof context.lock === 'object' &&
          (await original.revalidateSingleWriter?.(context)) === true
        )
      },
    })
  }

  #credentials(attemptId: string) {
    const r = this.#resources!
    return {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attemptId,
    }
  }

  /**
   * 耐久済み本文をそのまま1回送り、同slotのACKだけを同期済みへする。
   * 実GETは行わない（呼出元がACK対象をまとめて照合する）。
   */
  async #sendOnce(slot: DurableQueueSlot): Promise<InternalOperationResult> {
    const r = this.#resources!
    if (slot.state !== queueStateId('未送信'))
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR,
      }
    const stored = await r.envelopes.read({
      tenantId: this.#identity.tenantId!,
      gameId: this.#gameId,
      d4: r.grant.d4,
      d1: slot.d1,
      d5: String(slot.d5),
    })
    if (!stored)
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    let body: unknown
    try {
      body = JSON.parse(stored.requestJson)
    } catch {
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    }
    if (!isGameLifecycleRequestBody(body))
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const action = actionOf(body)
    if (action === null)
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const kind = this.#resolveEventKind(action)
    if (!kind)
      return {
        kind: 'blocked',
        reason:
          action === 'reopen'
            ? GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE
            : GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    const rebuilt = buildGameLifecycleRequestBody({
      gameId: this.#gameId,
      recordingRightProof: body.recording_right_proof,
      slot,
      action,
      eventKind: kind,
    })
    if (!rebuilt.ok || !sameOrdinaryWire(rebuilt.body, body))
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    if (body.recording_right_proof !== r.grant.recording_right_proof)
      return { kind: 'blocked', reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED }
    this.#assert()
    try {
      await r.dispatches.mark(
        {
          tenantId: this.#identity.tenantId!,
          gameId: this.#gameId,
          d4: r.grant.d4,
          d5: String(slot.d5),
        },
        stored.attemptId,
      )
    } catch {
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.DURABILITY_UNAVAILABLE,
      }
    }
    const sent = await postGameLifecycleRequestBody(
      this.#gameId,
      rebuilt.body,
      this.#credentials(stored.attemptId),
    )
    if (!sent.sent)
      return {
        kind: 'pending',
        reason: GAME_LIFECYCLE_REASON.SEND_NOT_ACCEPTED,
        ...(sent.status === undefined ? {} : { status: sent.status }),
      }
    this.#assert()
    const ack = readOrdinaryPitchAck(sent.response, {
      d4: r.grant.d4,
      d1: slot.d1,
      d5: String(slot.d5),
    })
    const applied = await applyAckToSlot(
      { scope: this.#scope(), d1: slot.d1, ack },
      r.queue,
    )
    this.#assert()
    if (applied.outcome !== 'applied')
      return { kind: 'pending', reason: GAME_LIFECYCLE_REASON.ACK_NOT_APPLIED }
    this.#saveAck = ackKind(sent.response) ?? this.#saveAck
    return { kind: 'acked', ack: this.#saveAck, d1: slot.d1 }
  }

  async #commit(
    action: GameLifecycleAction,
  ): Promise<GameLifecycleOperationResult> {
    if (this.#busy)
      return { outcome: 'blocked', reason: GAME_LIFECYCLE_REASON.BUSY }
    this.#busy = true
    this.#saveAck = null
    this.#failure = null
    let accepted = false
    try {
      await this.#open()
      // baseが無い初回だけ実GETを試す。失敗しても先行slotと耐久baseが無ければ
      // 依存refを作れないため、閉じて返す。
      if (!this.#base) {
        const ok = await this.#refreshInternal()
        if (!ok)
          return {
            outcome: 'blocked',
            reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_REQUIRED,
          }
      }
      const result = await runAsSingleWriter<GameLifecycleOperationResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const base = this.#base
          if (!base)
            return {
              outcome: 'blocked' as const,
              reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_REQUIRED,
            }
          const snapshot = await this.#snapshot(base)
          if (snapshot.truncated)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.SCAN_TRUNCATED,
            }
          const precondition = this.#precondition(action, snapshot)
          if (!precondition.ok)
            return {
              outcome: 'blocked' as const,
              reason: precondition.reason,
            }
          if (snapshot.foreignPrepared)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.FOREIGN_PREPARED_ENVELOPE,
            }
          if (snapshot.preparedOrphan)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE,
            }
          const kind = this.#resolveEventKind(action)
          if (!kind)
            return {
              outcome: 'blocked' as const,
              reason:
                action === 'reopen'
                  ? GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE
                  : GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          const checkpointRef = this.#checkpointRef(snapshot, base)
          if (!checkpointRef.ok)
            return {
              outcome: 'blocked' as const,
              reason: checkpointRef.reason,
            }
          let target: GameLifecycleReopenTarget | null = null
          if (action === 'reopen') {
            const selected = this.#reopenTarget(snapshot, base)
            if (!selected.ok)
              return { outcome: 'blocked' as const, reason: selected.reason }
            target = selected.value
          }
          const d2 = this.#nextD2(snapshot, base)
          if (!d2.ok) return { outcome: 'blocked' as const, reason: d2.reason }
          const d1 = snapshot.nextD1
          const d5 = crypto.randomUUID()
          let event: SyncEvent
          try {
            const payload = buildGameLifecyclePayload({
              action,
              checkpointRef: checkpointRef.value,
              target,
              event: {
                eventId: crypto.randomUUID(),
                receiptId: crypto.randomUUID(),
              },
            })
            event = buildGameLifecycleSyncEvent({
              gameId: this.#gameId,
              d4: base.d4,
              d5,
              d2: d2.value,
              payload,
              eventKind: kind,
            })
          } catch {
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          }
          const draft: DurableQueueSlot = {
            game: this.#gameId,
            d4: base.d4,
            d1,
            d5,
            version: 1,
            event,
            state: queueStateId('未送信'),
          }
          const built = buildGameLifecycleRequestBody({
            gameId: this.#gameId,
            recordingRightProof: this.#resources!.grant.recording_right_proof,
            slot: draft,
            action,
            eventKind: kind,
          })
          if (!built.ok)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          const attemptId = crypto.randomUUID()
          try {
            const stored = await this.#resources!.envelopes.prepare(
              {
                tenantId: this.#identity.tenantId!,
                gameId: this.#gameId,
                d4: base.d4,
                d1,
                d5,
                body: built.body,
                event,
              },
              attemptId,
            )
            if (stored.attemptId !== attemptId)
              return {
                outcome: 'blocked' as const,
                reason: GAME_LIFECYCLE_REASON.DURABILITY_UNAVAILABLE,
              }
          } catch {
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.DURABILITY_UNAVAILABLE,
            }
          }
          this.#assert()
          const appended = await appendPitchEventUnderLock(
            {
              gameIdentifier: this.#gameId,
              scope: this.#scope(),
              d5,
              version: 1,
              event,
            },
            this.#resources!.queue,
          )
          this.#assert()
          if (appended.outcome !== 'accepted')
            return appended.outcome === 'undetermined'
              ? {
                  outcome: 'pending' as const,
                  reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
                }
              : {
                  outcome: 'blocked' as const,
                  reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_REJECTED,
                }
          accepted = true
          if (appended.slot.d1 !== d1 || appended.slot.d5 !== d5)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          const verified = buildGameLifecycleRequestBody({
            gameId: this.#gameId,
            recordingRightProof: built.body.recording_right_proof,
            slot: appended.slot,
            action,
            eventKind: kind,
          })
          if (!verified.ok || !sameOrdinaryWire(verified.body, built.body))
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          if (snapshot.oldestUnsettled)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
            }
          const sent = await this.#sendOnce(appended.slot)
          if (sent.kind !== 'acked') return publicResult(sent)
          const after = await this.#snapshot(base)
          const expected = this.#expectedAfter(base, after, sent.d1)
          if (!expected.ok)
            return {
              outcome: 'blocked' as const,
              reason: expected.reason,
            }
          const refreshed = await this.#refreshInternal({
            action,
            minimumD1: sent.d1,
            expectedStatus: expected.value.expectedStatus,
            expectedLastVersion: expected.value.expectedLastVersion,
            expectedTarget: expected.value.expectedTarget,
          })
          return {
            outcome: 'acked' as const,
            ack: sent.ack,
            refresh: refreshed ? 'done' : 'pending',
          }
        },
        this.#injections(),
      )
      const value: GameLifecycleOperationResult = result.recordingStarted
        ? result.value
        : {
            outcome: 'blocked',
            reason: GAME_LIFECYCLE_REASON.LOCK_UNAVAILABLE,
          }
      try {
        if (this.#base) this.#scan = await this.#snapshot(this.#base)
      } catch {
        // 走査できないことを操作結果の変更として扱わない。
      }
      if (value.outcome === 'acked') {
        if (value.refresh === 'done') this.#failure = null
      } else this.#failure = value.reason
      return value
    } catch {
      const reason = !this.#current()
        ? GAME_LIFECYCLE_REASON.IDENTITY_CHANGED
        : accepted
          ? GAME_LIFECYCLE_REASON.SEND_NOT_ACCEPTED
          : GAME_LIFECYCLE_REASON.OPERATION_FAILED
      this.#failure = reason
      return accepted
        ? { outcome: 'pending', reason }
        : { outcome: 'blocked', reason }
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }

  /** 試合終了を宣言する。通信断中でも耐久queueへ保存する。 */
  end(): Promise<GameLifecycleOperationResult> {
    return this.#commit('end')
  }

  /** 追記のために再開する。先行終了が未確定でも durable chain で表現する。 */
  reopen(): Promise<GameLifecycleOperationResult> {
    return this.#commit('reopen')
  }

  /**
   * 順序が来たlifecycle要求だけを、同本文/同D5/同attemptで送る。
   * 先行の非lifecycle slotは既入力の再送に譲り、ここでは飛ばさない。
   */
  async retry(): Promise<GameLifecycleOperationResult> {
    if (this.#busy)
      return { outcome: 'blocked', reason: GAME_LIFECYCLE_REASON.BUSY }
    this.#busy = true
    this.#failure = null
    try {
      await this.#open()
      if (!this.#base) {
        const ok = await this.#refreshInternal()
        if (!ok)
          return {
            outcome: 'blocked',
            reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_REQUIRED,
          }
      }
      const result = await runAsSingleWriter<GameLifecycleOperationResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const base = this.#base
          if (!base)
            return {
              outcome: 'blocked' as const,
              reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_REQUIRED,
            }
          let lastSentD1: number | null = null
          for (let attempt = 0; attempt < RETRY_CHAIN_LIMIT; attempt += 1) {
            const snapshot = await this.#snapshot(base)
            if (snapshot.truncated)
              return {
                outcome: 'pending' as const,
                reason: GAME_LIFECYCLE_REASON.SCAN_TRUNCATED,
              }
            if (snapshot.broken)
              return {
                outcome: 'blocked' as const,
                reason: GAME_LIFECYCLE_REASON.INVALID_LOCAL_STATE,
              }
            if (snapshot.rejectedLifecycle)
              return {
                outcome: 'blocked' as const,
                reason: GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR,
              }
            if (snapshot.preparedOrphan) {
              const resumed = await this.#resumePrepared(
                snapshot,
                snapshot.preparedOrphan,
              )
              if (resumed.kind !== 'acked') return publicResult(resumed)
              lastSentD1 = resumed.d1
              continue
            }
            const head = snapshot.oldestUnsettled
            if (!head) break
            if (!isLifecycleSlot(head))
              return {
                outcome: 'pending' as const,
                reason: GAME_LIFECYCLE_REASON.PENDING_PREDECESSOR,
              }
            if (head.state !== queueStateId('未送信'))
              return {
                outcome: 'blocked' as const,
                reason: GAME_LIFECYCLE_REASON.REQUIRES_OPERATOR,
              }
            const sent = await this.#sendOnce(head)
            if (sent.kind !== 'acked') return publicResult(sent)
            lastSentD1 = sent.d1
          }
          if (lastSentD1 === null) {
            const refreshed = await this.#refreshInternal()
            if (refreshed)
              return {
                outcome: 'acked' as const,
                ack: this.#saveAck,
                refresh: 'done' as const,
              }
            return {
              outcome: 'pending' as const,
              reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_FAILED,
            }
          }
          const after = await this.#snapshot(base)
          const expected = this.#expectedAfter(base, after, lastSentD1)
          if (!expected.ok)
            return { outcome: 'blocked' as const, reason: expected.reason }
          const refreshed = await this.#refreshInternal({
            action: after.lastLifecycle?.action ?? 'end',
            minimumD1: lastSentD1,
            expectedStatus: expected.value.expectedStatus,
            expectedLastVersion: expected.value.expectedLastVersion,
            expectedTarget: expected.value.expectedTarget,
          })
          return {
            outcome: 'acked' as const,
            ack: this.#saveAck,
            refresh: refreshed ? 'done' : 'pending',
          }
        },
        this.#injections(),
      )
      const value: GameLifecycleOperationResult = result.recordingStarted
        ? result.value
        : {
            outcome: 'blocked',
            reason: GAME_LIFECYCLE_REASON.LOCK_UNAVAILABLE,
          }
      try {
        if (this.#base) this.#scan = await this.#snapshot(this.#base)
      } catch {
        // 走査できないことを再送結果の変更として扱わない。
      }
      this.#failure = value.outcome === 'acked' ? null : value.reason
      return value
    } catch {
      const reason = this.#current()
        ? GAME_LIFECYCLE_REASON.SEND_NOT_ACCEPTED
        : GAME_LIFECYCLE_REASON.IDENTITY_CHANGED
      this.#failure = reason
      return { outcome: 'pending', reason }
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }

  /** queue未受理の準備行を、同じevent/本文/D5のまま受理へ進める。 */
  async #resumePrepared(
    snapshot: Snapshot,
    stored: StoredNativeEnvelope,
  ): Promise<InternalOperationResult> {
    const base = this.#base!
    let body: unknown
    try {
      body = JSON.parse(stored.requestJson)
    } catch {
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    }
    if (!isGameLifecycleRequestBody(body))
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const action = actionOf(body)
    if (action === null)
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const kind = this.#resolveEventKind(action)
    if (!kind)
      return {
        kind: 'blocked',
        reason:
          action === 'reopen'
            ? GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE
            : GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    if (
      body.recording_right_proof !==
      this.#resources!.grant.recording_right_proof
    )
      return { kind: 'blocked', reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED }
    const draft: DurableQueueSlot = {
      game: this.#gameId,
      d4: base.d4,
      d1: stored.d1,
      d5: stored.d5,
      version: 1,
      event: stored.event,
      state: queueStateId('未送信'),
    }
    const rebuilt = buildGameLifecycleRequestBody({
      gameId: this.#gameId,
      recordingRightProof: body.recording_right_proof,
      slot: draft,
      action,
      eventKind: kind,
    })
    if (!rebuilt.ok || !sameOrdinaryWire(rebuilt.body, body))
      return {
        kind: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    if (snapshot.oldestUnsettled && snapshot.oldestUnsettled.d1 < stored.d1)
      return {
        kind: 'pending',
        reason: GAME_LIFECYCLE_REASON.PENDING_PREDECESSOR,
      }
    const appended = await appendPitchEventUnderLock(
      {
        gameIdentifier: this.#gameId,
        scope: this.#scope(),
        d5: stored.d5,
        version: 1,
        event: stored.event,
      },
      this.#resources!.queue,
    )
    this.#assert()
    if (appended.outcome !== 'accepted')
      return appended.outcome === 'undetermined'
        ? {
            kind: 'pending',
            reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
          }
        : {
            kind: 'blocked',
            reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_REJECTED,
          }
    if (appended.slot.d1 !== stored.d1)
      return {
        kind: 'pending',
        reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
      }
    return this.#sendOnce(appended.slot)
  }

  #closeIfDisposed(): void {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.envelopes.close()
      this.#resources?.dispatches.close()
      this.#resources?.bases.close()
      this.#resources = null
    }
  }

  dispose(): void {
    this.#disposed = true
    this.#closeIfDisposed()
  }
}

/** ACK対象の確定版/receipt、またはそれ以後の真正pointerかを判定する。 */
function matchesExpected(
  game: GameLifecycleGame,
  expected: Readonly<{
    action: GameLifecycleAction
    minimumD1: number
    expectedStatus: GameLifecycleStatus
    expectedLastVersion: string
    expectedTarget: GameLifecycleTarget | null
  }>,
): boolean {
  const d3 = BigInt(game.checkpoint.content.d3)
  const minimumD1 = BigInt(expected.minimumD1)
  const version = BigInt(game.lifecycle.lastVersion)
  const expectedVersion = BigInt(expected.expectedLastVersion)
  if (d3 < minimumD1 || version < expectedVersion) return false
  // 同じD1で別の終了版にはならない。より先の真正GETだけを後続結果とする。
  if (version > expectedVersion) return d3 > minimumD1
  if (game.status !== expected.expectedStatus) {
    // 再開は終了版を増やさない。同版の後続reopenを古い終了GETと区別する。
    return (
      d3 > minimumD1 &&
      expected.expectedStatus === 'finished' &&
      game.status === 'in_progress' &&
      game.lifecycle.active === null
    )
  }
  if (expected.expectedStatus === 'finished') {
    const target = expected.expectedTarget
    return (
      target !== null &&
      game.lifecycle.active !== null &&
      game.lifecycle.active.eventId === target.eventId &&
      game.lifecycle.active.receiptId === target.receiptId
    )
  }
  return game.lifecycle.active === null
}

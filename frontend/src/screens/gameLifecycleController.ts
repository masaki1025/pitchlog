// 終了・追記再開の実画面controller。
//
// 順序は docs/features/mvp-lifecycle-ui/plan.md の固定に従う:
//   1. 単一書き手の排他を待たずに取る
//   2. 実GETで現在の CP と status/active を読む
//   3. D5/D1/D2/予約event/receipt/attempt/V12込み全本文を IndexedDB へ strict commit
//   4. 既存 queue へ追記し、追記が成立した時点を受理とする
//   5. 保存した本文をそのまま送る（再作成しない）
//   6. 既存 ACK 機構で同 slot の受理/重複だけを同期済みへ
//   7. 実GETで status/active/最終更新を再取得する
//
// 保存ACKと再取得未了は別状態で返す。固定成功応答や新D5への置換は行わない。
import {
  buildGameLifecyclePayload,
  buildGameLifecycleRequestBody,
  buildGameLifecycleSyncEvent,
  gameLifecycleEventKind,
  isGameLifecycleRequestBody,
  postGameLifecycleRequestBody,
  readGameLifecycle,
  type GameLifecycleAction,
  type GameLifecycleGame,
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
const QUEUE_SCAN_LIMIT = 1000
/** lifecycle payload の識別。queue slot がこのunitの操作かを値から判定する。 */
const LIFECYCLE_PAYLOAD_FORMAT = 'native-game-lifecycle-v1'
/** 送信を1度でも試みたかを残す小さな耐久store。未送信と結果不明を分ける。 */
const DISPATCH_DATABASE = 'pitchlog-game-lifecycle-dispatch'
const DISPATCH_STORE = 'dispatched'

type DispatchKey = Readonly<{
  tenantId: string
  gameId: string
  d4: string
  d5: string
}>

function dispatchKey(key: DispatchKey): IDBValidKey {
  return [key.tenantId, key.gameId, key.d4, key.d5] as IDBValidKey
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
    if (!globalThis.isSecureContext || !globalThis.indexedDB)
      throw new Error('送信マーカーを保存できません')
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = globalThis.indexedDB.open(DISPATCH_DATABASE, 1)
      request.onerror = () => reject(new Error('送信マーカーを開けません'))
      request.onblocked = () => reject(new Error('送信マーカーを開けません'))
      request.onupgradeneeded = () => {
        request.result.createObjectStore(DISPATCH_STORE, {
          keyPath: ['tenantId', 'gameId', 'd4', 'd5'],
        })
      }
      request.onsuccess = () => resolve(request.result)
    })
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
      const transaction = this.#database.transaction(
        DISPATCH_STORE,
        'readwrite',
        {
          durability: 'strict',
        },
      )
      if (transaction.durability !== 'strict') {
        transaction.abort()
        reject(new Error('送信マーカーを確定できません'))
        return
      }
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
  /** 操作の前提status/activeが実GETと食い違う。 */
  STATUS_MISMATCH: 'status-mismatch',
  /** 再開種別が正本の写しに無い（root追補待ち）。 */
  REOPEN_KIND_UNAVAILABLE: 'reopen-kind-unavailable',
  /** 同じqueueに先行の未終結slotがあり、追記は受理したが送信していない。 */
  QUEUED_AWAITING_PREDECESSOR: 'queued-awaiting-predecessor',
  /** 同じqueueに先行の未終結slotがある。飛ばさない。 */
  PENDING_PREDECESSOR: 'pending-predecessor',
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
  /** 再送する未確定操作が無い。 */
  NOTHING_PENDING: 'nothing-pending',
  /** 要操作slotが残っている。自動再送しない。 */
  REQUIRES_OPERATOR: 'requires-operator',
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
  status: GameLifecycleStatus | null
  lastVersion: string | null
  active: GameLifecycleTarget | null
  activeStatsVersionId: string | null
  lastSavedAt: string | null
  nextPosition: Readonly<{ d1: string; d2: string }> | null
  recoveryGeneration: string | null
  checkpointRef: Readonly<{
    id: string
    revision: string
    digest: string
  }> | null
  /** lifecycle projection の有限page件数。全履歴を表さない。 */
  pageItemCount: number
  hasNextPage: boolean
  /** 未送信のlifecycle操作（準備行あり）＝結果不明。 */
  unknownCount: number
  /** 未送信のlifecycle操作（送信をまだ試みていない）。 */
  preparedCount: number
  /** lifecycle操作のうち送信本文を復元できない。 */
  unpreparedCount: number
  /** 他の操作の未終結slot。 */
  otherUnsettledCount: number
  scanTruncated: boolean
  saveAck: GameLifecycleAck | null
  refresh: GameLifecycleRefreshState
  /** 直近の実GETが失敗し、表示が最終取得時点のままである。 */
  stale: boolean
  lastFailure: GameLifecycleReason | null
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
      /** 応答が返った場合の状態コード。 */
      status?: number
    }>
  | Readonly<{
      outcome: 'acked'
      /** 前回の適用済みでACK種別を再確認できない場合は null。 */
      ack: GameLifecycleAck | null
      /** 実GETでの再取得が済んだか。pendingでも保存ACKは成立している。 */
      refresh: 'done' | 'pending'
    }>

type Resources = Readonly<{
  queue: DurableQueue
  envelopes: NativeEnvelopePersistence
  dispatches: LifecycleDispatchPersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}>

type Scan = Readonly<{
  /** 未終結の先頭（種別を問わない）。 */
  oldest: DurableQueueSlot | null
  /** 未終結のlifecycle操作の先頭。 */
  oldestLifecycle: DurableQueueSlot | null
  /** lifecycle操作のうち、送信をまだ試みていない。 */
  preparedCount: number
  /** lifecycle操作のうち、送信を試みたが受理を確認できていない。 */
  unknownCount: number
  /** lifecycle操作のうち、送信本文を復元できない。 */
  unpreparedCount: number
  otherUnsettledCount: number
  prepared: StoredNativeEnvelope | null
  foreignPrepared: boolean
  truncated: boolean
}>

type Precondition =
  Readonly<{ ok: true }> | Readonly<{ ok: false; reason: GameLifecycleReason }>

export type GameLifecycleControllerOptions = Readonly<{
  writer?: SingleWriterInjections
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

/** 終了/追記再開を、既queue・既排他・既ACK・実GETへ接続する。 */
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
  #game: GameLifecycleGame | null = null
  #scan: Scan | null = null
  #saveAck: GameLifecycleAck | null = null
  #refresh: GameLifecycleRefreshState = 'idle'
  #failure: GameLifecycleReason | null = null
  #busy = false
  #disposed = false

  constructor(
    gameId: string,
    readIdentity: () => FirstBallIdentity,
    options: GameLifecycleControllerOptions = {},
  ) {
    this.#gameId = gameId
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
    this.#writer = options.writer ?? {}
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
        this.#assert()
        this.#resources = {
          queue,
          envelopes,
          dispatches,
          device,
          grant: start.grant,
        }
        queue = null
        envelopes = null
        dispatches = null
      } finally {
        store?.close()
        queue?.close()
        envelopes?.close()
        dispatches?.close()
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
    return { ok: true, game }
  }

  /** 同一game/D4の有限pageだけを走査する。全件走査を装わない。 */
  async #scanQueue(): Promise<Scan> {
    const r = this.#resources!
    const scope = this.#scope()
    let cursor: number | null = null
    let oldest: DurableQueueSlot | null = null
    let oldestLifecycle: DurableQueueSlot | null = null
    let preparedCount = 0
    let unknownCount = 0
    let unpreparedCount = 0
    let otherUnsettledCount = 0
    let seen = 0
    let truncated = false
    do {
      const page = await r.queue.readSlotsPage(scope, cursor, 100)
      for (const slot of page.items) {
        seen += 1
        if (seen > QUEUE_SCAN_LIMIT) {
          truncated = true
          break
        }
        if (!isUnsettled(slot)) continue
        if (!oldest) oldest = slot
        if (!isLifecycleSlot(slot)) {
          otherUnsettledCount += 1
          continue
        }
        if (!oldestLifecycle) oldestLifecycle = slot
        try {
          const stored = await r.envelopes.read({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            d4: r.grant.d4,
            d1: slot.d1,
            d5: String(slot.d5),
          })
          if (!stored) {
            unpreparedCount += 1
            continue
          }
          const dispatched = await r.dispatches.has({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            d4: r.grant.d4,
            d5: String(slot.d5),
          })
          if (dispatched) unknownCount += 1
          else preparedCount += 1
        } catch {
          // 読めない準備行を「送信済み」とも「未送信」とも補完しない。
          unpreparedCount += 1
        }
      }
      if (truncated) break
      cursor = page.nextCursorD1
    } while (cursor !== null)

    let prepared: StoredNativeEnvelope | null = null
    let foreignPrepared = false
    if (!oldest) {
      const next = await r.queue.readNextD1(scope)
      const occupied = await r.queue.readSlot(scope, next)
      if (!occupied) {
        const candidate = await r.envelopes.readPreparedSlot({
          tenantId: this.#identity.tenantId!,
          gameId: this.#gameId,
          d4: r.grant.d4,
          d1: next,
        })
        if (candidate) {
          if (isLifecycleEvent(candidate.event)) prepared = candidate
          else foreignPrepared = true
        }
      }
    }
    return {
      oldest,
      oldestLifecycle,
      preparedCount,
      unknownCount,
      unpreparedCount,
      otherUnsettledCount,
      prepared,
      foreignPrepared,
      truncated,
    }
  }

  async #refreshInternal(): Promise<boolean> {
    const fresh = await this.#readFresh()
    if (!fresh.ok) {
      this.#refresh = 'failed'
      this.#failure = fresh.reason
      return false
    }
    let scan: Scan
    try {
      scan = await this.#scanQueue()
    } catch {
      this.#refresh = 'failed'
      this.#failure = GAME_LIFECYCLE_REASON.STORAGE_UNAVAILABLE
      return false
    }
    this.#game = fresh.game
    this.#scan = scan
    this.#refresh = 'done'
    this.#failure = null
    return true
  }

  #precondition(
    action: GameLifecycleAction,
    game: GameLifecycleGame,
  ): Precondition {
    if (
      game.status !== game.lifecycle.status ||
      game.lifecycle.active?.version !==
        (game.lifecycle.active === null
          ? undefined
          : game.lifecycle.lastVersion)
    )
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STATUS_MISMATCH }
    if (action === 'end') {
      if (
        game.status !== 'in_progress' ||
        game.lifecycle.status !== 'in_progress' ||
        game.lifecycle.active !== null
      )
        return { ok: false, reason: GAME_LIFECYCLE_REASON.STATUS_MISMATCH }
    } else if (
      game.status !== 'finished' ||
      game.lifecycle.status !== 'finished' ||
      game.lifecycle.active === null
    )
      return { ok: false, reason: GAME_LIFECYCLE_REASON.STATUS_MISMATCH }
    return { ok: true }
  }

  get view(): GameLifecycleView {
    const game = this.#game
    const scan = this.#scan
    const active = game?.lifecycle.active ?? null
    const status = game?.status ?? null
    const endKind = this.#resolveEventKind('end')
    const reopenKind = this.#resolveEventKind('reopen')
    const pendingLifecycle =
      scan !== null && (scan.oldestLifecycle !== null || scan.prepared !== null)
    const unavailable = scan === null || scan.truncated
    const resumeHandoff: GameLifecycleHandoff | null =
      status === 'in_progress' &&
      game !== null &&
      !this.#busy &&
      !pendingLifecycle &&
      !unavailable
        ? {
            gameId: game.id,
            tenantId: game.checkpoint.content.scope.tenantId,
            nextPosition: { ...game.next_position },
            checkpointRef: { ...game.checkpoint.ref },
            recoveryGeneration: game.recovery_generation,
            lastSavedAt: game.last_saved_at,
          }
        : null
    return {
      status,
      lastVersion: game?.lifecycle.lastVersion ?? null,
      active,
      activeStatsVersionId: game?.lifecycle.activeStatsVersionId ?? null,
      lastSavedAt: game?.last_saved_at ?? null,
      nextPosition: game ? { ...game.next_position } : null,
      recoveryGeneration: game?.recovery_generation ?? null,
      checkpointRef: game ? { ...game.checkpoint.ref } : null,
      pageItemCount: game?.page.items.length ?? 0,
      hasNextPage: game !== null && game.page.next_cursor !== null,
      unknownCount: scan?.unknownCount ?? 0,
      preparedCount: scan?.preparedCount ?? 0,
      unpreparedCount: scan?.unpreparedCount ?? 0,
      otherUnsettledCount: scan?.otherUnsettledCount ?? 0,
      scanTruncated: scan?.truncated ?? false,
      saveAck: this.#saveAck,
      refresh: this.#refresh,
      stale: this.#refresh === 'failed',
      lastFailure: this.#failure,
      reopenBlocked: status === 'finished' && reopenKind === undefined,
      canEnd:
        status === 'in_progress' &&
        endKind !== undefined &&
        !this.#busy &&
        !pendingLifecycle &&
        !unavailable &&
        this.#refresh !== 'failed',
      canReopen:
        status === 'finished' &&
        active !== null &&
        reopenKind !== undefined &&
        !this.#busy &&
        !pendingLifecycle &&
        !unavailable &&
        this.#refresh !== 'failed',
      canRetry:
        !this.#busy &&
        scan !== null &&
        ((scan.oldest !== null && isLifecycleSlot(scan.oldest)) ||
          scan.prepared !== null ||
          scan.foreignPrepared),
      busy: this.#busy,
      resumeHandoff,
    }
  }

  /** 実GETとqueueの有限走査で表示を復元する。保存成功を作らない。 */
  async refresh(): Promise<GameLifecycleView> {
    if (this.#busy) return this.view
    this.#busy = true
    try {
      await this.#open()
      await this.#refreshInternal()
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
   * 保存済み本文をそのまま1回送り、同slotのACKだけを同期済みへする。
   *
   * Args:
   *     slot: 受理済みのqueue slot。
   *     body: queue受理前に耐久storeへ確定した本文。
   *
   * Returns:
   *     ACKの成否と、実GET再取得の成否。
   */
  async #dispatch(
    slot: DurableQueueSlot,
    body: GameLifecycleRequestBody,
  ): Promise<GameLifecycleOperationResult> {
    const r = this.#resources!
    const stored = await r.envelopes.read({
      tenantId: this.#identity.tenantId!,
      gameId: this.#gameId,
      d4: r.grant.d4,
      d1: slot.d1,
      d5: String(slot.d5),
    })
    if (!stored)
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    if (!sameOrdinaryWire(JSON.parse(stored.requestJson), body))
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    // 再送で新しいgrantのV12へ書き換えない。資格が変わったら送らない。
    if (body.recording_right_proof !== r.grant.recording_right_proof)
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED,
      }
    this.#assert()
    // 送信を試みたことを先に耐久確定する。以後の停止は「結果不明」と表示する。
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
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.DURABILITY_UNAVAILABLE,
      }
    }
    const sent = await postGameLifecycleRequestBody(
      this.#gameId,
      body,
      this.#credentials(stored.attemptId),
    )
    if (!sent.sent)
      return {
        outcome: 'pending',
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
      return {
        outcome: 'pending',
        reason: GAME_LIFECYCLE_REASON.ACK_NOT_APPLIED,
      }
    this.#saveAck = ackKind(sent.response) ?? this.#saveAck
    const refreshed = await this.#refreshInternal()
    return {
      outcome: 'acked',
      ack: this.#saveAck,
      refresh: refreshed ? 'done' : 'pending',
    }
  }

  /** 受理済みslotを再送する。新D5/新本文を作らない。 */
  async #resend(slot: DurableQueueSlot): Promise<GameLifecycleOperationResult> {
    const r = this.#resources!
    if (slot.state !== queueStateId('未送信'))
      return {
        outcome: 'blocked',
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
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    let body: unknown
    try {
      body = JSON.parse(stored.requestJson)
    } catch {
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    }
    const action =
      typeof body === 'object' && body !== null && !Array.isArray(body)
        ? actionOf(body as GameLifecycleRequestBody)
        : null
    if (action === null)
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const kind = this.#resolveEventKind(action)
    if (!kind)
      return {
        outcome: 'blocked',
        reason:
          action === 'reopen'
            ? GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE
            : GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    const rebuilt = buildGameLifecycleRequestBody({
      gameId: this.#gameId,
      recordingRightProof: (body as GameLifecycleRequestBody)
        .recording_right_proof,
      slot,
      action,
      eventKind: kind,
    })
    if (!rebuilt.ok || !sameOrdinaryWire(rebuilt.body, body))
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    return this.#dispatch(slot, rebuilt.body)
  }

  /** queue未受理の準備行を、同じevent/本文/D5のまま受理へ進める。 */
  async #resumePrepared(
    stored: StoredNativeEnvelope,
  ): Promise<GameLifecycleOperationResult> {
    const r = this.#resources!
    let body: unknown
    try {
      body = JSON.parse(stored.requestJson)
    } catch {
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    }
    if (!isGameLifecycleRequestBody(body))
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const action = actionOf(body)
    if (action === null)
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE_UNAVAILABLE,
      }
    const kind = this.#resolveEventKind(action)
    if (!kind)
      return {
        outcome: 'blocked',
        reason:
          action === 'reopen'
            ? GAME_LIFECYCLE_REASON.REOPEN_KIND_UNAVAILABLE
            : GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    if (body.recording_right_proof !== r.grant.recording_right_proof)
      return {
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.GRANT_CHANGED,
      }
    const draft: DurableQueueSlot = {
      game: this.#gameId,
      d4: r.grant.d4,
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
        outcome: 'blocked',
        reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
      }
    const appended = await appendPitchEventUnderLock(
      {
        gameIdentifier: this.#gameId,
        scope: this.#scope(),
        d5: stored.d5,
        version: 1,
        event: stored.event,
      },
      r.queue,
    )
    this.#assert()
    if (appended.outcome !== 'accepted')
      return appended.outcome === 'undetermined'
        ? {
            outcome: 'pending',
            reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
          }
        : {
            outcome: 'blocked',
            reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_REJECTED,
          }
    if (appended.slot.d1 !== stored.d1)
      return {
        outcome: 'pending',
        reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
      }
    return this.#dispatch(appended.slot, rebuilt.body)
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
      const result = await runAsSingleWriter<GameLifecycleOperationResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const scan = await this.#scanQueue()
          if (scan.truncated)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.SCAN_TRUNCATED,
            }
          if (scan.foreignPrepared)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.FOREIGN_PREPARED_ENVELOPE,
            }
          // 未確定のlifecycle操作が残る間は二重に宣言しない。先行する通常球などは
          // 追記を禁じない（FR-010: 未同期プレイがあっても終了宣言はキューへ積む）。
          if (scan.oldestLifecycle || scan.prepared)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.PREPARED_ENVELOPE,
            }
          const fresh = await this.#readFresh()
          if (!fresh.ok)
            return {
              outcome: 'blocked' as const,
              reason: fresh.reason,
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
          const precondition = this.#precondition(action, fresh.game)
          if (!precondition.ok)
            return {
              outcome: 'blocked' as const,
              reason: precondition.reason,
            }
          this.#game = fresh.game
          const r = this.#resources!
          const scope = this.#scope()
          let d1: number
          try {
            d1 = await r.queue.readNextD1(scope)
          } catch {
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
            }
          }
          const d2 = Number(fresh.game.next_position.d2)
          if (!Number.isSafeInteger(d1) || d1 < 1)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.QUEUE_APPEND_UNDETERMINED,
            }
          if (!Number.isSafeInteger(d2) || d2 < 0)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.REQUEST_BODY_MISMATCH,
            }
          const d5 = crypto.randomUUID()
          let event: SyncEvent
          try {
            const payload = buildGameLifecyclePayload({
              action,
              checkpointRef: fresh.game.checkpoint.ref,
              target: action === 'reopen' ? fresh.game.lifecycle.active : null,
              event: {
                eventId: crypto.randomUUID(),
                receiptId: crypto.randomUUID(),
              },
            })
            event = buildGameLifecycleSyncEvent({
              gameId: this.#gameId,
              d4: r.grant.d4,
              d5,
              d2,
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
            d4: r.grant.d4,
            d1,
            d5,
            version: 1,
            event,
            state: queueStateId('未送信'),
          }
          const built = buildGameLifecycleRequestBody({
            gameId: this.#gameId,
            recordingRightProof: r.grant.recording_right_proof,
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
            const stored = await r.envelopes.prepare(
              {
                tenantId: this.#identity.tenantId!,
                gameId: this.#gameId,
                d4: r.grant.d4,
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
              scope,
              d5,
              version: 1,
              event,
            },
            r.queue,
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
          // 未終結の先行slotを飛ばして送らない。追記は受理済みとして保持し、
          // 先行分が同期された後の再送で順に送る（FR-010 の断中宣言）。
          if (scan.oldest && scan.oldest.d1 < appended.slot.d1)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.QUEUED_AWAITING_PREDECESSOR,
            }
          return this.#dispatch(appended.slot, built.body)
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
        this.#scan = await this.#scanQueue()
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

  /** 試合終了を宣言する。status=in_progress・active=null のときだけ。 */
  end(): Promise<GameLifecycleOperationResult> {
    return this.#commit('end')
  }

  /** 追記のために再開する。targetは直GETの最新active全3値に限る。 */
  reopen(): Promise<GameLifecycleOperationResult> {
    return this.#commit('reopen')
  }

  /** 結果不明は既slot/原本文/attemptだけを再送。新CPや新D5へ置換しない。 */
  async retry(): Promise<GameLifecycleOperationResult> {
    if (this.#busy)
      return { outcome: 'blocked', reason: GAME_LIFECYCLE_REASON.BUSY }
    this.#busy = true
    this.#failure = null
    try {
      await this.#open()
      const result = await runAsSingleWriter<GameLifecycleOperationResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const scan = await this.#scanQueue()
          if (scan.truncated)
            return {
              outcome: 'pending' as const,
              reason: GAME_LIFECYCLE_REASON.SCAN_TRUNCATED,
            }
          if (scan.oldest) {
            if (!isLifecycleSlot(scan.oldest))
              return {
                outcome: 'pending' as const,
                reason: GAME_LIFECYCLE_REASON.PENDING_PREDECESSOR,
              }
            return this.#resend(scan.oldest)
          }
          if (scan.foreignPrepared)
            return {
              outcome: 'blocked' as const,
              reason: GAME_LIFECYCLE_REASON.FOREIGN_PREPARED_ENVELOPE,
            }
          if (scan.prepared) return this.#resumePrepared(scan.prepared)
          const refreshed = await this.#refreshInternal()
          if (refreshed)
            return {
              outcome: 'acked',
              ack: this.#saveAck,
              refresh: 'done',
            }
          return {
            outcome: 'pending',
            reason: this.#failure ?? GAME_LIFECYCLE_REASON.READ_FAILED,
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
        this.#scan = await this.#scanQueue()
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

  #closeIfDisposed(): void {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.envelopes.close()
      this.#resources?.dispatches.close()
      this.#resources = null
    }
  }

  dispose(): void {
    this.#disposed = true
    this.#closeIfDisposed()
  }
}

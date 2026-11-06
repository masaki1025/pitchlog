/** 正式P1/P2、既耐久slot/attempt/排他/ACKを接合する。保存成功を推測しない。 */
import type { Observations } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import { readCompleteUndoGame } from '../api/nativeUndoGame'
import {
  nativeUndoBody,
  postNativeUndo,
  NATIVE_UNDO_KIND,
  NativeEnvelopePersistence,
} from '../api/nativeUndoWire'
import {
  buildSyncEventRequestBody,
  postSyncEvents,
  type SyncEventSendRequest,
} from '../api/client.syncEvents'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { readOrdinaryPitchAck } from '../api/ordinaryPitchAck'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import {
  singleWriterLockName,
  runAsSingleWriter,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import { queueStateId } from '../lib/sync/queueState'
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import { PITCH_EVENT_KIND } from './GameScreenPitchEvent'
import { appendPitchEventUnderLock } from './GameScreenPitchAcceptance'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import { applyAckToSlot } from './GameScreenAckApplication'
import {
  prepareNativeUndo,
  prepareBallAfterUndo,
  type UndoProductContext,
} from './GameScreenUndoProductProvider'
export type UndoProductResult =
  'ready' | 'empty' | 'saved' | 'saved-awaiting-read' | 'pending' | 'blocked'
type Resources = {
  queue: DurableQueue
  attempts: NativeEnvelopePersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}
export class GameScreenUndoProductController {
  #gameId: string
  #readIdentity: () => FirstBallIdentity
  #identity: FirstBallIdentity
  #writer: SingleWriterInjections
  #resources: Resources | null = null
  #context: UndoProductContext | null = null
  #busy = false
  #disposed = false
  constructor(
    gameId: string,
    readIdentity: () => FirstBallIdentity,
    writer: SingleWriterInjections = {},
  ) {
    this.#gameId = gameId
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
    this.#writer = writer
  }
  get context(): UndoProductContext | null {
    return this.#context === null ? null : structuredClone(this.#context)
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
      throw new Error('認証文脈が変わりました')
  }
  #scope() {
    return { game: this.#gameId, d4: this.#resources!.grant.d4 }
  }
  async #open() {
    this.#assert()
    if (this.#resources) return
    let store: GameStartPersistence | null = null,
      queue: DurableQueue | null = null,
      attempts: NativeEnvelopePersistence | null = null
    try {
      store = await GameStartPersistence.open()
      const tenant = this.#identity.tenantId!,
        device = await store.readDevice(tenant),
        start = await store.readStart(tenant, this.#gameId)
      this.#assert()
      if (
        !device ||
        !start ||
        start.status !== 'received' ||
        !start.grant ||
        device.device_id !== start.grant.device_id
      )
        throw new Error('端末の開始資格がありません')
      queue = await openDurableQueue({
        databaseName: 'pitchlog-first-ball-queue-' + tenant,
      })
      attempts = await NativeEnvelopePersistence.open()
      this.#assert()
      this.#resources = { queue, attempts, device, grant: start.grant }
      queue = null
      attempts = null
    } finally {
      store?.close()
      queue?.close()
      attempts?.close()
    }
  }
  async #oldest(): Promise<DurableQueueSlot | null> {
    let cursor: number | null = null
    do {
      const page = await this.#resources!.queue.readSlotsPage(
        this.#scope(),
        cursor,
        100,
      )
      this.#assert()
      const slot = page.items.find(
        (s) =>
          s.state === queueStateId('未送信') ||
          s.state === queueStateId('要操作'),
      )
      if (slot) return slot
      cursor = page.nextCursorD1
    } while (cursor !== null)
    return null
  }
  async #prepared() {
    const r = this.#resources!
    const d1 = await r.queue.readNextD1(this.#scope())
    if ((await r.queue.readSlot(this.#scope(), d1)) !== undefined)
      throw new Error('未受理位置を照合できません')
    this.#assert()
    return r.attempts.readPreparedSlot({
      tenantId: this.#identity.tenantId!,
      gameId: this.#gameId,
      d4: r.grant.d4,
      d1,
    })
  }
  /** 封筒commit後/queue受理前の停止を原要求だけで復旧する。 */
  async #resumePrepared(): Promise<UndoProductResult> {
    const prepared = await this.#prepared()
    this.#assert()
    if (!prepared) return 'ready'
    await this.#read()
    const c = this.#context!,
      r = this.#resources!
    const event = prepared.event
    const payload = event.fields.V7 as Record<string, unknown>
    const calculation = payload.calculation as {
      request?: { prefixRef?: unknown }
    }
    const checkpoint =
      event.fields.V5 === NATIVE_UNDO_KIND.id
        ? payload.expectedCheckpoint
        : calculation?.request?.prefixRef
    if (
      !sameOrdinaryWire(checkpoint, c.source.checkpoint.ref) ||
      Number(c.game.next_position.d1) !== prepared.d1 ||
      c.game.current_d4 !== r.grant.d4 ||
      c.game.recovery_generation !== r.grant.recovery_generation ||
      (event.fields.V5 !== NATIVE_UNDO_KIND.id && !c.storedNative)
    )
      return 'blocked'
    const original = JSON.parse(prepared.requestJson)
    if (
      original.recording_right_proof !== r.grant.recording_right_proof ||
      c.game.lineups.away.lineup_id !== r.grant.away_lineup_id ||
      c.game.lineups.home.lineup_id !== r.grant.home_lineup_id
    )
      return 'blocked'
    const proposed: DurableQueueSlot = {
      game: this.#gameId,
      d4: r.grant.d4,
      d1: prepared.d1,
      d5: prepared.d5,
      version: 1,
      event,
      state: queueStateId('未送信'),
    }
    if (
      !sameOrdinaryWire(
        this.#wire(proposed, original.recording_right_proof).body,
        original,
      )
    )
      return 'blocked'
    const accepted = await appendPitchEventUnderLock(
      {
        gameIdentifier: this.#gameId,
        scope: this.#scope(),
        d5: prepared.d5,
        version: 1,
        event,
      },
      r.queue,
    )
    this.#assert()
    if (accepted.outcome !== 'accepted')
      return accepted.outcome === 'undetermined' ? 'pending' : 'blocked'
    if (
      accepted.slot.d1 !== prepared.d1 ||
      !sameOrdinaryWire(
        this.#wire(accepted.slot, original.recording_right_proof).body,
        original,
      )
    )
      return 'pending'
    return this.#send(accepted.slot)
  }
  async #read(): Promise<void> {
    this.#assert()
    const read = await readCompleteUndoGame(
      this.#gameId,
      this.#identity.tenantId!,
    )
    this.#assert()
    this.#context = { ...read, tenantId: this.#identity.tenantId! }
  }
  async load(): Promise<UndoProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#read()
      try {
        await this.#open()
      } catch {
        return 'blocked'
      }
      return (await this.#oldest()) || (await this.#prepared())
        ? 'pending'
        : 'ready'
    } catch {
      this.#context = null
      return 'blocked'
    } finally {
      this.#busy = false
      this.#close()
    }
  }
  #injections(): SingleWriterInjections {
    const original = this.#writer
    return withNonBlockingSingleWriter({
      ...original,
      revalidateSingleWriter: async (c) => {
        this.#assert()
        return (
          c.gameIdentifier === this.#gameId &&
          c.lockName === singleWriterLockName(this.#gameId) &&
          c.lock !== null &&
          typeof c.lock === 'object' &&
          (await original.revalidateSingleWriter?.(c)) === true
        )
      },
    })
  }
  #wire(slot: DurableQueueSlot, proof: unknown) {
    const request: SyncEventSendRequest = {
      gameId: this.#gameId,
      recordingRightProof: proof,
      slots: [slot],
      eventKinds: [PITCH_EVENT_KIND],
    }
    const body =
      slot.event.fields.V5 === NATIVE_UNDO_KIND.id
        ? nativeUndoBody(slot, proof)
        : buildSyncEventRequestBody(request)
    if (!('events' in body)) throw new Error('原要求を形成できません')
    return { request, body }
  }
  async #send(slot: DurableQueueSlot): Promise<UndoProductResult> {
    this.#assert()
    const r = this.#resources!
    if (slot.state !== queueStateId('未送信') || typeof slot.d5 !== 'string')
      return 'pending'
    const durable = await r.queue.readSlot(this.#scope(), slot.d1)
    this.#assert()
    if (!durable || !sameOrdinaryWire(durable, slot)) return 'pending'
    const undo = slot.event.fields.V5 === NATIVE_UNDO_KIND.id
    // 再送で新しいgrantのV12へ書換えず、queue受理前に確定した封筒だけを使う。
    const attempt = await r.attempts.read({
      tenantId: this.#identity.tenantId!,
      gameId: this.#gameId,
      d4: r.grant.d4,
      d1: slot.d1,
      d5: slot.d5,
    })
    this.#assert()
    if (!attempt) return 'blocked'
    const original: unknown = JSON.parse(attempt.requestJson)
    if (
      !original ||
      typeof original !== 'object' ||
      !('recording_right_proof' in original)
    )
      return 'blocked'
    const { request, body } = this.#wire(slot, original.recording_right_proof)
    if (!sameOrdinaryWire(original, body)) return 'blocked'
    const credentials = {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attempt.attemptId,
    }
    let response: unknown
    try {
      if (undo)
        response = await postNativeUndo(
          this.#gameId,
          nativeUndoBody(slot, original.recording_right_proof),
          credentials,
        )
      else {
        const sent = await postSyncEvents({
          ...request,
          syncCredentials: credentials,
        })
        if (!sent.sent) return 'pending'
        response = sent.response
      }
    } catch {
      return 'pending'
    }
    this.#assert()
    const ack = readOrdinaryPitchAck(response, {
      d4: r.grant.d4,
      d1: slot.d1,
      d5: slot.d5,
    })
    const applied = await applyAckToSlot(
      { scope: this.#scope(), d1: slot.d1, ack },
      r.queue,
    )
    this.#assert()
    if (applied.outcome !== 'applied') return 'pending'
    this.#context = null
    try {
      await this.#read()
      return 'saved'
    } catch {
      return 'saved-awaiting-read'
    }
  }
  async #commit(
    kind: 'undo' | 'ball',
    observations?: Observations,
  ): Promise<UndoProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    let accepted = false
    try {
      await this.#open()
      const offered = this.#context?.source.checkpoint.ref
      if (!offered) return 'blocked'
      const result = await runAsSingleWriter<UndoProductResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          if ((await this.#oldest()) || (await this.#prepared()))
            return 'pending'
          await this.#read()
          const c = this.#context!,
            r = this.#resources!
          if (
            !sameOrdinaryWire(offered, c.source.checkpoint.ref) ||
            c.game.current_d4 !== r.grant.d4 ||
            c.game.recovery_generation !== r.grant.recovery_generation ||
            c.game.lineups.away.lineup_id !== r.grant.away_lineup_id ||
            c.game.lineups.home.lineup_id !== r.grant.home_lineup_id
          )
            return 'blocked'
          if (kind === 'ball' && !c.storedNative) return 'blocked'
          if (kind === 'undo' && c.source.activeStack.length === 0)
            return 'empty'
          const expected = Number(c.game.next_position.d1)
          if (
            !Number.isSafeInteger(expected) ||
            (await r.queue.readNextD1(this.#scope())) !== expected
          )
            return 'blocked'
          const d5 = crypto.randomUUID(),
            event =
              kind === 'undo'
                ? prepareNativeUndo(c, d5)
                : observations
                  ? prepareBallAfterUndo(
                      c,
                      observations,
                      {
                        d5,
                        eventId: crypto.randomUUID(),
                        playId: crypto.randomUUID(),
                      },
                      crypto.randomUUID(),
                    )
                  : null
          if (event === null) return 'empty'
          // 仮slotはwire形成用であり受理済みではない。IDB strict commitが先、queue受理が後。
          const proposed: DurableQueueSlot = {
            game: this.#gameId,
            d4: r.grant.d4,
            d1: expected,
            d5,
            version: 1,
            event,
            state: queueStateId('未送信'),
          }
          const prepared = this.#wire(proposed, r.grant.recording_right_proof)
          await r.attempts.prepare({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            d4: r.grant.d4,
            d1: expected,
            d5,
            body: prepared.body,
            event,
          })
          this.#assert()
          const a = await appendPitchEventUnderLock(
            {
              gameIdentifier: this.#gameId,
              scope: this.#scope(),
              d5,
              version: 1,
              event,
            },
            r.queue,
          )
          this.#assert()
          if (a.outcome !== 'accepted')
            return a.outcome === 'undetermined' ? 'pending' : 'blocked'
          accepted = true
          if (
            a.slot.d1 !== expected ||
            !sameOrdinaryWire(
              this.#wire(a.slot, r.grant.recording_right_proof).body,
              prepared.body,
            )
          )
            return 'pending'
          return this.#send(a.slot)
        },
        this.#injections(),
      )
      return result.recordingStarted ? result.value : 'blocked'
    } catch {
      return accepted ? 'pending' : 'blocked'
    } finally {
      this.#busy = false
      this.#close()
    }
  }
  undo(): Promise<UndoProductResult> {
    return this.#commit('undo')
  }
  ball(observations: Observations): Promise<UndoProductResult> {
    return this.#commit('ball', observations)
  }
  /** 結果不明は既slot/原body/attemptだけを再送。新CPや新D5へ置換しない。 */
  async retry(): Promise<UndoProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const result = await runAsSingleWriter<UndoProductResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const slot = await this.#oldest()
          return slot ? this.#send(slot) : this.#resumePrepared()
        },
        this.#injections(),
      )
      return result.recordingStarted ? result.value : 'blocked'
    } catch {
      return 'pending'
    } finally {
      this.#busy = false
      this.#close()
    }
  }
  #close() {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.attempts.close()
      this.#resources = null
      this.#context = null
    }
  }
  dispose() {
    this.#disposed = true
    this.#close()
  }
}

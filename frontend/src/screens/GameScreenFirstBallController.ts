import type { StartedGameRead } from '../api/startedGame'
import {
  buildSyncEventRequestBody,
  postSyncEvents,
  type SyncEventSendRequest,
} from '../api/client.syncEvents'
import type { SyncRequestCredentials } from '../api/client'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
import { FirstBallAttemptPersistence } from '../lib/firstBallAttemptPersistence'
import { openDurableQueue, type DurableQueue } from '../lib/sync/durableQueue'
import {
  singleWriterLockName,
  runAsSingleWriter,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import { queueStateId } from '../lib/sync/queueState'
import { PITCH_EVENT_KIND } from './GameScreenPitchEvent'
import { commitPitchEvent } from './GameScreenPitchCommit'
import { applyAckToSlot } from './GameScreenAckApplication'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import { readFirstBallAck } from '../api/firstBallWire'
import {
  prepareFirstBall,
  firstBallEvent,
  type FirstBallScreenObservation,
  type FirstBallVocabulary,
} from './GameScreenFirstBallProvider'

export type FirstBallIdentity = Readonly<{
  tenantId: string | null
  epoch: number
  verified: boolean
}>
export type FirstBallOperationResult =
  'ready' | 'recorded' | 'saved' | 'pending' | 'blocked'
type Resources = {
  queue: DurableQueue
  attempts: FirstBallAttemptPersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}
const eventKinds = [PITCH_EVENT_KIND]

/** 初球の実資格・耐久queue・attemptを接続する。新しい計算や保存結果を作らない。 */
export class GameScreenFirstBallController {
  #game: StartedGameRead
  #identity: FirstBallIdentity
  #readIdentity: () => FirstBallIdentity
  #resources: Resources | null = null
  #disposed = false
  #busy = false
  #singleWriter: SingleWriterInjections
  #opening: Promise<void> | null = null
  constructor(
    game: StartedGameRead,
    readIdentity: () => FirstBallIdentity,
    singleWriter: SingleWriterInjections = {},
  ) {
    this.#game = structuredClone(game)
    this.#singleWriter = singleWriter
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
  }
  #current(): boolean {
    const now = this.#readIdentity()
    return (
      !this.#disposed &&
      now.verified &&
      this.#identity.verified &&
      now.tenantId === this.#identity.tenantId &&
      now.epoch === this.#identity.epoch &&
      now.tenantId !== null
    )
  }
  #assert(): void {
    if (!this.#current()) throw new Error('初球の操作前提を確認できません')
  }
  async #open(): Promise<void> {
    this.#assert()
    if (this.#resources) return
    if (this.#opening) return this.#opening
    this.#opening = (async () => {
      const tenant = this.#identity.tenantId!
      let store: GameStartPersistence | null = null
      let queue: DurableQueue | null = null
      let attempts: FirstBallAttemptPersistence | null = null
      try {
        store = await GameStartPersistence.open()
        const device = await store.readDevice(tenant)
        const start = await store.readStart(tenant, this.#game.id)
        this.#assert()
        if (
          !device ||
          !start ||
          start.status !== 'received' ||
          !start.grant ||
          device.device_id !== start.grant.device_id ||
          start.grant.d4 !== this.#game.current_d4 ||
          start.grant.away_lineup_id !== this.#game.lineups.away.lineup_id ||
          start.grant.home_lineup_id !== this.#game.lineups.home.lineup_id
        )
          throw new Error('開始資格を確認できません')
        queue = await openDurableQueue({
          databaseName: 'pitchlog-first-ball-queue-' + tenant,
        })
        attempts = await FirstBallAttemptPersistence.open()
        this.#assert()
        this.#resources = { queue, attempts, device, grant: start.grant }
        queue = null
        attempts = null
      } finally {
        store?.close()
        queue?.close()
        attempts?.close()
      }
    })()
    try {
      await this.#opening
    } finally {
      this.#opening = null
    }
  }
  #scope() {
    return { game: this.#game.id, d4: this.#game.current_d4 }
  }
  #writerInjections(): SingleWriterInjections {
    const original = this.#singleWriter
    return {
      ...original,
      revalidateSingleWriter: async (context) => {
        if (
          !this.#current() ||
          !this.#resources ||
          context.gameIdentifier !== this.#game.id ||
          context.lockName !== singleWriterLockName(this.#game.id) ||
          context.lock === null ||
          typeof context.lock !== 'object'
        )
          return false
        if ((await original.revalidateSingleWriter?.(context)) !== true)
          return false
        const next = await this.#resources.queue.readNextD1(this.#scope())
        return Number.isSafeInteger(next) && next >= 1 && this.#current()
      },
    }
  }
  async inspect(): Promise<FirstBallOperationResult> {
    try {
      await this.#open()
      this.#assert()
      const r = this.#resources!
      const slot = await r.queue.readSlot(this.#scope(), 1)
      const pending = await r.attempts.read(
        this.#identity.tenantId!,
        this.#game.id,
      )
      this.#assert()
      if (slot?.state === queueStateId('同期済み')) return 'saved'
      return slot || pending
        ? 'pending'
        : this.#game.read_kind === 'recorded'
          ? 'recorded'
          : 'ready'
    } catch {
      return 'blocked'
    }
  }
  async #credentials(
    request: SyncEventSendRequest,
  ): Promise<SyncRequestCredentials> {
    this.#assert()
    const r = this.#resources!
    if (request.slots.length !== 1 || request.slots[0]!.d1 !== 1)
      throw new Error('初球以外の要求です')
    const body = buildSyncEventRequestBody(request)
    if (!('events' in body)) throw new Error('初球の送信形式が不正です')
    const slot = request.slots[0]!
    if (typeof slot.d5 !== 'string') throw new Error('要求識別が不正です')
    const attempt = await r.attempts.prepare({
      tenantId: this.#identity.tenantId!,
      gameId: this.#game.id,
      d5: slot.d5,
      events: body.events,
    })
    this.#assert()
    return {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attempt.attemptId,
    }
  }
  async submit(
    observation: FirstBallScreenObservation,
    vocabulary: FirstBallVocabulary,
  ): Promise<FirstBallOperationResult> {
    if (this.#busy || this.#game.read_kind !== 'initial') return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      this.#assert()
      const r = this.#resources!,
        prepared = prepareFirstBall(
          this.#game,
          observation,
          vocabulary,
          this.#identity.tenantId!,
        ),
        d5 = crypto.randomUUID()
      let key: { d4: string; d1: number; d5: string } | null = null
      const beforeAppend = async () => {
        this.#assert()
        if (
          (await r.queue.readNextD1(this.#scope())) !== 1 ||
          (await r.attempts.read(this.#identity.tenantId!, this.#game.id)) !==
            null
        )
          throw new Error('既存要求の終結を確認してください')
        this.#assert()
      }
      const result = await commitPitchEvent(
        {
          gameIdentifier: this.#game.id,
          scope: this.#scope(),
          d5,
          version: 1,
          event: firstBallEvent(prepared, { d5, d2: 1 }),
          recordingRightProof: r.grant.recording_right_proof,
          eventKinds,
        },
        {
          queue: r.queue,
          singleWriterInjections: this.#writerInjections(),
          beforeAppend,
          prepareSend: async (request) => {
            key = { d4: this.#game.current_d4, d1: request.slots[0]!.d1, d5 }
            return this.#credentials(request)
          },
          readAck: (value) =>
            this.#current() && key !== null
              ? readFirstBallAck(value, key)
              : undefined,
        },
      )
      this.#assert()
      if (
        result.outcome === 'attempted' &&
        result.ackApplication?.outcome === 'applied'
      )
        return 'saved'
      return (await r.queue.readSlot(this.#scope(), 1)) ? 'pending' : 'blocked'
    } catch {
      if (this.#resources && this.#current()) {
        try {
          return (await this.#resources.queue.readSlot(this.#scope(), 1))
            ? 'pending'
            : 'blocked'
        } catch {
          return 'pending'
        }
      }
      return 'blocked'
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }
  /** 旧slotを再読して送る。再採番・再追記・元要求の置換は行わない。 */
  async retry(): Promise<FirstBallOperationResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const r = this.#resources!
      this.#assert()
      const result = await runAsSingleWriter<FirstBallOperationResult>(
        { gameIdentifier: this.#game.id },
        async () => {
          this.#assert()
          const slot = await r.queue.readSlot(this.#scope(), 1)
          if (!slot) return 'blocked'
          if (
            (await r.attempts.read(this.#identity.tenantId!, this.#game.id)) ===
            null
          )
            return 'blocked'
          if (slot.state === queueStateId('同期済み')) return 'saved'
          if (
            slot.state !== queueStateId('未送信') ||
            typeof slot.d5 !== 'string'
          )
            return 'pending'
          const request: SyncEventSendRequest = {
            gameId: this.#game.id,
            recordingRightProof: r.grant.recording_right_proof,
            slots: [slot],
            eventKinds,
          }
          const syncCredentials = await this.#credentials(request)
          this.#assert()
          const sent = await postSyncEvents({ ...request, syncCredentials })
          if (!sent.sent) return 'pending'
          this.#assert()
          const ack = readFirstBallAck(sent.response, {
            d4: this.#game.current_d4,
            d1: slot.d1,
            d5: slot.d5,
          })
          const applied = await applyAckToSlot(
            { scope: this.#scope(), d1: slot.d1, ack },
            r.queue,
          )
          this.#assert()
          return applied.outcome === 'applied' ? 'saved' : 'pending'
        },
        withNonBlockingSingleWriter(this.#writerInjections()),
      )
      return result.recordingStarted ? result.value : 'blocked'
    } catch {
      return 'pending'
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }
  #closeIfDisposed() {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.attempts.close()
      this.#resources = null
    }
  }
  dispose(): void {
    this.#disposed = true
    this.#closeIfDisposed()
  }
}

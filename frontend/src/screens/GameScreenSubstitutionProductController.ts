/** 交代の原本文/attempt/queue/D1 ACKを同一書き手へ束ねる。 */
import { readSubstitutionContext } from '../api/substitutionRead'
import {
  isSubstitutionPayload,
  postSubstitution,
  substitutionBody,
  SUBSTITUTION_KIND,
} from '../api/substitutionWire'
import { NativeEnvelopePersistence } from '../api/nativeUndoWire'
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
import { appendPitchEventUnderLock } from './GameScreenPitchAcceptance'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import { applyAckToSlot } from './GameScreenAckApplication'
import {
  prepareSubstitution,
  substitutionContextKey,
  type VerifiedSubstitutionContext,
} from './GameScreenSubstitutionProductProvider'
import type { RawSubstitutionDraft } from './GameScreenSubstitutionTypes'

export type SubstitutionProductResult =
  'ready' | 'saved' | 'saved-awaiting-read' | 'pending' | 'blocked'

type Resources = {
  queue: DurableQueue
  attempts: NativeEnvelopePersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}

export class GameScreenSubstitutionProductController {
  #gameId: string
  #readIdentity: () => FirstBallIdentity
  #identity: FirstBallIdentity
  #writer: SingleWriterInjections
  #resources: Resources | null = null
  #context: VerifiedSubstitutionContext | null = null
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

  get context(): VerifiedSubstitutionContext | null {
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

  async #open(): Promise<void> {
    this.#assert()
    if (this.#resources) return
    let store: GameStartPersistence | null = null
    let queue: DurableQueue | null = null
    let attempts: NativeEnvelopePersistence | null = null
    try {
      store = await GameStartPersistence.open()
      const tenant = this.#identity.tenantId!
      const device = await store.readDevice(tenant)
      const start = await store.readStart(tenant, this.#gameId)
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

  async #read(): Promise<void> {
    this.#assert()
    const context = await readSubstitutionContext(
      this.#gameId,
      this.#identity.tenantId!,
    )
    this.#assert()
    this.#context = context
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

  #grantMatches(c: VerifiedSubstitutionContext): boolean {
    const grant = this.#resources!.grant
    return (
      c.generation === grant.d4 &&
      c.recoveryGeneration === grant.recovery_generation &&
      c.awayLineupId === grant.away_lineup_id &&
      c.homeLineupId === grant.home_lineup_id
    )
  }

  #wire(slot: DurableQueueSlot, proof: unknown) {
    if (slot.event.fields.V5 !== SUBSTITUTION_KIND.id)
      throw new Error('交代以外のqueueイベントです')
    return substitutionBody(slot, proof)
  }

  async #send(slot: DurableQueueSlot): Promise<SubstitutionProductResult> {
    this.#assert()
    const r = this.#resources!
    if (slot.state !== queueStateId('未送信') || typeof slot.d5 !== 'string')
      return 'pending'
    const durable = await r.queue.readSlot(this.#scope(), slot.d1)
    this.#assert()
    if (!durable || !sameOrdinaryWire(durable, slot)) return 'pending'
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
    const proof = original.recording_right_proof
    if (!sameOrdinaryWire(original, this.#wire(slot, proof))) return 'blocked'
    const sent = await postSubstitution(slot, proof, {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attempt.attemptId,
    })
    this.#assert()
    if (!sent.sent) return 'pending'
    const ack = readOrdinaryPitchAck(sent.response, {
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

  async #resumePrepared(): Promise<SubstitutionProductResult> {
    const prepared = await this.#prepared()
    if (!prepared) return 'ready'
    await this.#read()
    const c = this.#context!
    const r = this.#resources!
    const payload = prepared.event.fields.V7
    if (
      prepared.event.fields.V5 !== SUBSTITUTION_KIND.id ||
      !isSubstitutionPayload(payload) ||
      !sameOrdinaryWire(payload.expectedCheckpoint, c.checkpoint) ||
      c.nextD1 !== prepared.d1 ||
      !this.#grantMatches(c)
    )
      return 'blocked'
    const original: unknown = JSON.parse(prepared.requestJson)
    if (
      !original ||
      typeof original !== 'object' ||
      !('recording_right_proof' in original) ||
      original.recording_right_proof !== r.grant.recording_right_proof
    )
      return 'blocked'
    const proposed: DurableQueueSlot = {
      game: this.#gameId,
      d4: r.grant.d4,
      d1: prepared.d1,
      d5: prepared.d5,
      version: 1,
      event: prepared.event,
      state: queueStateId('未送信'),
    }
    if (
      !sameOrdinaryWire(
        original,
        this.#wire(proposed, original.recording_right_proof),
      )
    )
      return 'blocked'
    const accepted = await appendPitchEventUnderLock(
      {
        gameIdentifier: this.#gameId,
        scope: this.#scope(),
        d5: prepared.d5,
        version: 1,
        event: prepared.event,
      },
      r.queue,
    )
    this.#assert()
    if (accepted.outcome !== 'accepted')
      return accepted.outcome === 'undetermined' ? 'pending' : 'blocked'
    if (
      accepted.slot.d1 !== prepared.d1 ||
      !sameOrdinaryWire(
        this.#wire(accepted.slot, original.recording_right_proof),
        original,
      )
    )
      return 'pending'
    return this.#send(accepted.slot)
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

  async load(): Promise<SubstitutionProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#read()
      await this.#open()
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

  async commit(
    draft: RawSubstitutionDraft,
  ): Promise<SubstitutionProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    let accepted = false
    try {
      await this.#open()
      const offered = this.#context
      if (!offered) return 'blocked'
      const result = await runAsSingleWriter<SubstitutionProductResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          if ((await this.#oldest()) || (await this.#prepared()))
            return 'pending'
          await this.#read()
          const c = this.#context!
          const r = this.#resources!
          if (
            substitutionContextKey(c) !== substitutionContextKey(offered) ||
            !this.#grantMatches(c) ||
            (await r.queue.readNextD1(this.#scope())) !== c.nextD1
          )
            return 'blocked'
          const d5 = crypto.randomUUID()
          const prepared = prepareSubstitution(
            c,
            draft,
            d5,
            crypto.randomUUID(),
          )
          if (!prepared) return 'blocked'
          const proposed: DurableQueueSlot = {
            game: this.#gameId,
            d4: r.grant.d4,
            d1: c.nextD1,
            d5,
            version: 1,
            event: prepared.event,
            state: queueStateId('未送信'),
          }
          const body = this.#wire(proposed, r.grant.recording_right_proof)
          await r.attempts.prepare({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            d4: r.grant.d4,
            d1: c.nextD1,
            d5,
            body,
            event: prepared.event,
          })
          this.#assert()
          const queued = await appendPitchEventUnderLock(
            {
              gameIdentifier: this.#gameId,
              scope: this.#scope(),
              d5,
              version: 1,
              event: prepared.event,
            },
            r.queue,
          )
          this.#assert()
          if (queued.outcome !== 'accepted')
            return queued.outcome === 'undetermined' ? 'pending' : 'blocked'
          accepted = true
          if (
            queued.slot.d1 !== c.nextD1 ||
            !sameOrdinaryWire(
              this.#wire(queued.slot, r.grant.recording_right_proof),
              body,
            )
          )
            return 'pending'
          return this.#send(queued.slot)
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

  async retry(): Promise<SubstitutionProductResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const result = await runAsSingleWriter<SubstitutionProductResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const slot = await this.#oldest()
          if (slot && slot.event.fields.V5 !== SUBSTITUTION_KIND.id)
            return 'pending'
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

  #close(): void {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.attempts.close()
      this.#resources = null
      this.#context = null
    }
  }

  dispose(): void {
    this.#disposed = true
    this.#close()
  }
}

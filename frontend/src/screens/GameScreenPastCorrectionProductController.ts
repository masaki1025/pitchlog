/** 真正v3対象とD1なしP3原要求/I6を一つの書き手に束ねる。 */
import {
  readLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { fetchGameStats } from '../api/stats'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import {
  P3AttemptPersistence,
  type StoredP3Attempt,
} from '../lib/p3AttemptPersistence'
import { openDurableQueue, type DurableQueue } from '../lib/sync/durableQueue'
import { queueStateId } from '../lib/sync/queueState'
import {
  runAsSingleWriter,
  singleWriterLockName,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  p3ChangeBody,
  postP3Change,
  readP3ChangeConfirmation,
  readP3TargetOffer,
  type P3ChangeBody,
  type P3ReplacementResult,
  type P3TargetOffer,
} from '../api/pastCorrectionProduct'
import type { FirstBallObservations } from '../api/firstBallWire'
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'

export type P3ScreenResult =
  'ready' | 'saved' | 'saved-awaiting-read' | 'pending' | 'blocked'

type Resources = Readonly<{
  queue: DurableQueue
  attempts: P3AttemptPersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}>

export class GameScreenPastCorrectionProductController {
  #gameId: string
  #readIdentity: () => FirstBallIdentity
  #identity: FirstBallIdentity
  #writer: SingleWriterInjections
  #resources: Resources | null = null
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

  #assert(): void {
    const now = this.#readIdentity()
    if (
      this.#disposed ||
      !this.#identity.verified ||
      !now.verified ||
      !this.#identity.tenantId ||
      now.tenantId !== this.#identity.tenantId ||
      now.epoch !== this.#identity.epoch
    )
      throw new Error('P3の認証文脈が変わりました')
  }

  #scope() {
    return { game: this.#gameId, d4: this.#resources!.grant.d4 }
  }

  async #open(): Promise<void> {
    this.#assert()
    if (this.#resources) return
    let starts: GameStartPersistence | null = null
    let queue: DurableQueue | null = null
    let attempts: P3AttemptPersistence | null = null
    try {
      starts = await GameStartPersistence.open()
      const tenant = this.#identity.tenantId!
      const device = await starts.readDevice(tenant)
      const start = await starts.readStart(tenant, this.#gameId)
      this.#assert()
      if (
        !device ||
        !start ||
        start.status !== 'received' ||
        !start.grant ||
        device.device_id !== start.grant.device_id
      )
        throw new Error('P3の開始資格がありません')
      queue = await openDurableQueue({
        databaseName: 'pitchlog-first-ball-queue-' + tenant,
      })
      attempts = await P3AttemptPersistence.open()
      this.#assert()
      this.#resources = { queue, attempts, device, grant: start.grant }
      queue = null
      attempts = null
    } finally {
      starts?.close()
      queue?.close()
      attempts?.close()
    }
  }

  async #queueClear(): Promise<boolean> {
    const queue = this.#resources!.queue
    let cursor: number | null = null
    do {
      const page = await queue.readSlotsPage(this.#scope(), cursor, 100)
      this.#assert()
      if (
        page.items.some(
          (slot) =>
            slot.state === queueStateId('未送信') ||
            slot.state === queueStateId('要操作'),
        )
      )
        return false
      cursor = page.nextCursorD1
    } while (cursor !== null)
    return true
  }

  async #current(): Promise<LineupPrefixGame> {
    const result = await readLineupPrefixGame(this.#gameId, null, 25)
    this.#assert()
    if (
      result.kind !== 'found' ||
      result.game.page.next_cursor !== null ||
      result.game.status !== 'in_progress' ||
      result.game.prefix_ref.tenantId !== this.#identity.tenantId ||
      result.game.prefix_ref.gameId !== this.#gameId ||
      result.game.current_d4 !== this.#resources!.grant.d4 ||
      result.game.recovery_generation !==
        this.#resources!.grant.recovery_generation
    )
      throw new Error('P3の現v3原本を確認できません')
    return result.game
  }

  #offerMatches(game: LineupPrefixGame, offer: P3TargetOffer): boolean {
    const target = game.page.items[offer.target_reference.d1 - 1]?.play_row
    return (
      offer.target_reference.game === this.#gameId &&
      offer.target_reference.d4 === game.current_d4 &&
      sameOrdinaryWire(offer.expected_prefix_ref, game.prefix_ref) &&
      !!target &&
      offer.target_event_id === target.source_event_id &&
      offer.target_play_id === target.id &&
      offer.original_result_id === target.batting_result_key
    )
  }

  #writerInjections(): SingleWriterInjections {
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

  async inspect(d1: number): Promise<P3TargetOffer | null> {
    if (this.#busy) return null
    this.#busy = true
    try {
      await this.#open()
      if (
        !(await this.#queueClear()) ||
        (await this.#resources!.attempts.read(
          this.#identity.tenantId!,
          this.#gameId,
        ))
      )
        return null
      const game = await this.#current()
      const offer = await readP3TargetOffer(this.#gameId, d1)
      this.#assert()
      return this.#offerMatches(game, offer) ? offer : null
    } catch {
      return null
    } finally {
      this.#busy = false
      this.#close()
    }
  }

  async inspectPending(): Promise<P3ScreenResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const pending = await this.#resources!.attempts.read(
        this.#identity.tenantId!,
        this.#gameId,
      )
      this.#assert()
      return pending
        ? await this.#send(pending, false)
        : (await this.#queueClear())
          ? 'ready'
          : 'blocked'
    } catch {
      return 'blocked'
    } finally {
      this.#busy = false
      this.#close()
    }
  }

  async #readAfter(body: P3ChangeBody): Promise<boolean> {
    try {
      const game = await this.#current()
      const prior = body.change.payload.expectedPrefixRef
      const target =
        game.page.items[body.change.target_reference.d1 - 1]?.play_row
      if (
        !target ||
        target.id === body.change.payload.targetPlayId ||
        target.source_event_id === body.change.payload.targetEventId ||
        target.batting_result_key !== body.change.payload.replacementResultId ||
        game.prefix_ref.checkpoint.id === prior.checkpoint.id ||
        game.prefix_ref.checkpoint.digest === prior.checkpoint.digest ||
        game.prefix_ref.generation !== prior.generation ||
        BigInt(game.prefix_ref.length) < BigInt(prior.length) ||
        BigInt(game.prefix_ref.checkpoint.revision) <
          BigInt(prior.checkpoint.revision)
      )
        return false
      const confirmation = await readP3ChangeConfirmation(
        this.#gameId,
        body.change.target_reference.d1,
        body.change.d5,
      )
      this.#assert()
      if (
        confirmation.confirmed_version !== body.change.expected_version + 1 ||
        confirmation.d5 !== body.change.d5 ||
        !sameOrdinaryWire(
          confirmation.target_reference,
          body.change.target_reference,
        ) ||
        confirmation.source_event_id !== target.source_event_id ||
        confirmation.target_play_id !== target.id ||
        !sameOrdinaryWire(confirmation.current_prefix_ref, game.prefix_ref) ||
        !sameOrdinaryWire(confirmation.current_after, game.after)
      )
        return false
      const stats = await fetchGameStats(this.#gameId, 'current')
      this.#assert()
      return stats.game_id === this.#gameId && stats.mode === 'current'
    } catch {
      return false
    }
  }

  async #send(
    pending: StoredP3Attempt,
    submitIfMissing = true,
  ): Promise<P3ScreenResult> {
    this.#assert()
    const resources = this.#resources!
    const durable = await resources.attempts.read(
      this.#identity.tenantId!,
      this.#gameId,
    )
    this.#assert()
    if (!durable || !sameOrdinaryWire(durable, pending)) return 'pending'
    const body = JSON.parse(durable.requestJson) as P3ChangeBody
    if (
      durable.deviceId !== resources.device.device_id ||
      durable.d4 !== resources.grant.d4 ||
      body.recording_right_proof !== resources.grant.recording_right_proof ||
      body.recovery_generation !== resources.grant.recovery_generation ||
      !(await this.#queueClear())
    )
      return 'blocked'
    const storedI6 = await resources.queue.readI6(durable.d5)
    this.#assert()
    if (storedI6) {
      if (
        storedI6.source !== 'p3-acceptance' ||
        storedI6.state !== queueStateId('同期済み') ||
        storedI6.d5 !== durable.d5 ||
        storedI6.expectedVersion !== body.change.expected_version ||
        !sameOrdinaryWire(storedI6.targetReference, {
          試合: body.change.target_reference.game,
          '対象の D4': body.change.target_reference.d4,
          '対象の D1': body.change.target_reference.d1,
        }) ||
        !sameOrdinaryWire(storedI6.confirmedContent, body.change.payload)
      )
        return 'blocked'
      return (await this.#readAfter(body)) ? 'saved' : 'saved-awaiting-read'
    }
    if (!submitIfMissing) return 'pending'
    const result = await postP3Change(body, {
      deviceId: resources.device.device_id,
      deviceCredential: resources.device.device_credential,
      attempt: durable.attemptId,
    })
    this.#assert()
    if (result.kind !== 'accepted') return 'blocked'
    const accepted = {
      targetReference: result.targetReference,
      expectedVersion: result.expectedVersion,
      d5: result.d5,
      confirmedContent: result.confirmedContent,
    }
    const prepared = resources.queue.prepareI6Acceptance(accepted, {
      resolveAcceptedAt: () => ({
        known: true,
        targetReference: result.targetReference,
        acceptedAt: result.acceptedAt,
      }),
    })
    if (!prepared) return 'pending'
    const receipt = await resources.queue.persistI6Acceptance(prepared)
    this.#assert()
    if (!receipt) return 'pending'
    return (await this.#readAfter(body)) ? 'saved' : 'saved-awaiting-read'
  }

  async commit(
    offer: P3TargetOffer,
    replacementResultId: P3ReplacementResult,
    observations: FirstBallObservations,
  ): Promise<P3ScreenResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    let durable = false
    try {
      await this.#open()
      const outcome = await runAsSingleWriter<P3ScreenResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          if (
            !(await this.#queueClear()) ||
            (await this.#resources!.attempts.read(
              this.#identity.tenantId!,
              this.#gameId,
            ))
          )
            return 'pending'
          const game = await this.#current()
          const current = await readP3TargetOffer(
            this.#gameId,
            offer.target_reference.d1,
          )
          this.#assert()
          if (
            !sameOrdinaryWire(current, offer) ||
            !this.#offerMatches(game, current)
          )
            return 'blocked'
          const body = p3ChangeBody(
            current,
            crypto.randomUUID(),
            game.recovery_generation,
            this.#resources!.grant.recording_right_proof,
            replacementResultId,
            observations,
          )
          const pending = await this.#resources!.attempts.prepare({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            deviceId: this.#resources!.device.device_id,
            attemptId: crypto.randomUUID(),
            body,
          })
          durable = true
          this.#assert()
          return this.#send(pending)
        },
        this.#writerInjections(),
      )
      return outcome.recordingStarted ? outcome.value : 'blocked'
    } catch {
      return durable ? 'pending' : 'blocked'
    } finally {
      this.#busy = false
      this.#close()
    }
  }

  async retry(): Promise<P3ScreenResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const outcome = await runAsSingleWriter<P3ScreenResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          const pending = await this.#resources!.attempts.read(
            this.#identity.tenantId!,
            this.#gameId,
          )
          this.#assert()
          return pending ? this.#send(pending) : 'ready'
        },
        this.#writerInjections(),
      )
      return outcome.recordingStarted ? outcome.value : 'blocked'
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
    }
  }

  dispose(): void {
    this.#disposed = true
    this.#close()
  }
}

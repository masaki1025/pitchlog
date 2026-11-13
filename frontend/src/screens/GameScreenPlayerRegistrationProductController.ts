/**
 * その場登録（FR-015）の断中キュー・送信・A4 写像の製品制御。
 *
 * 登録は D1 付きキューの末尾へ追記してから送る。ACK の A4 写像は先に端末へ
 * 固定し、写像が確定するまでスロットを同期済みにしない（sync-protocol 4-4 の
 * C1〜C4）。交代が先に未送信で残っているときは、登録が追い越さない。
 */
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
import { readSubstitutionContext } from '../api/substitutionRead'
import { NativeEnvelopePersistence } from '../api/nativeUndoWire'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  isPlayerRegistrationInput,
  PLAYER_REGISTRATION_KIND,
  playerRegistrationBody,
  playerRegistrationEvent,
  playerRegistrationInput,
  postPlayerRegistration,
  readPlayerRegistrationAck,
} from '../api/playerRegistrationWire'
import {
  GameStartPersistence,
  type StoredGameStart,
} from '../lib/gameStartPersistence'
import {
  isPlayerRegistrationContext,
  PlayerRegistrationContextPersistence,
  type PlayerRegistrationContext,
} from '../lib/playerRegistrationContextPersistence'
import {
  TemporaryPlayerMappingConflictError,
  TemporaryPlayerMappingStore,
  type TemporaryPlayerMappingRecord,
} from '../lib/sync/temporaryPlayerMappingStore'
import {
  openDurableQueue,
  type DurableQueue,
  type DurableQueueSlot,
} from '../lib/sync/durableQueue'
import {
  runAsSingleWriter,
  singleWriterLockName,
  type SingleWriterInjections,
} from '../lib/sync/singleWriter'
import { queueStateId } from '../lib/sync/queueState'
import { applyAckToSlot } from './GameScreenAckApplication'
import { appendPitchEventUnderLock } from './GameScreenPitchAcceptance'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import { playerRegistration as playerRegistrationBodyFromDraft } from './GameScreenSubstitutionProductProvider'
import type { PlayerRegistrationDraft } from './GameScreenSubstitutionTypes'
import type { FirstBallIdentity } from './GameScreenFirstBallController'

export type PlayerRegistrationPanelResult = 'ready' | 'pending' | 'blocked'
export type PlayerRegistrationCommitResult =
  | 'saved'
  | 'queued'
  | 'pending'
  | 'ready'
  | 'invalid'
  | 'blocked'
  | 'awaiting-substitution'

export type PlayerRegistrationView = Readonly<{
  temporaryId: string
  name: string
  side: 'away' | 'home'
  d1: number
  state:
    'unsent' | 'confirmed' | 'action-required' | 'evacuated' | 'unconfirmed'
  officialId?: string
}>

type Resources = {
  queue: DurableQueue
  attempts: NativeEnvelopePersistence
  mappings: TemporaryPlayerMappingStore
  contexts: PlayerRegistrationContextPersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}

const REGISTRATION_KIND_ID = PLAYER_REGISTRATION_KIND.id
const UNSENT = queueStateId('未送信')
const ACTION_REQUIRED = queueStateId('要操作')
const SYNCED = queueStateId('同期済み')
const EVACUATED = queueStateId('退避済み')

/** 画面下書きを、一時 ID を固定した登録側原入力へ写す。 */
export function registrationInputFromDraft(
  draft: PlayerRegistrationDraft,
  teamId: string,
  temporaryId: string,
) {
  const body = playerRegistrationBodyFromDraft(draft, teamId)
  if (!body) return null
  try {
    return playerRegistrationInput({
      temporaryId,
      teamRecordId: body.team_record_id,
      name: body.name,
      throws: body.throws ?? null,
      bats: body.bats ?? null,
      uniformNumber: body.uniform_number ?? null,
      rosterStatusKey: body.roster_status_key,
    })
  } catch {
    return null
  }
}

export class GameScreenPlayerRegistrationProductController {
  #gameId: string
  #readIdentity: () => FirstBallIdentity
  #identity: FirstBallIdentity
  #writer: SingleWriterInjections
  #resources: Resources | null = null
  #context: PlayerRegistrationContext | null = null
  #views: readonly PlayerRegistrationView[] = []
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

  get registrations(): readonly PlayerRegistrationView[] {
    return Object.freeze([...this.#views])
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
    let mappings: TemporaryPlayerMappingStore | null = null
    let contexts: PlayerRegistrationContextPersistence | null = null
    try {
      store = await GameStartPersistence.open()
      const tenant = this.#identity.tenantId!
      const device = await store.readDevice(tenant)
      const start: StoredGameStart | null = await store.readStart(
        tenant,
        this.#gameId,
      )
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
      mappings = await TemporaryPlayerMappingStore.open()
      contexts = await PlayerRegistrationContextPersistence.open()
      this.#assert()
      this.#resources = {
        queue,
        attempts,
        mappings,
        contexts,
        device,
        grant: start.grant,
      }
      queue = null
      attempts = null
      mappings = null
      contexts = null
    } finally {
      store?.close()
      queue?.close()
      attempts?.close()
      mappings?.close()
      contexts?.close()
    }
  }

  async #readContext(): Promise<PlayerRegistrationContext> {
    const r = this.#resources!
    const tenant = this.#identity.tenantId!
    // オンラインで検証済みの文脈を優先し、同じ値を端末へ固定する。
    let online: Awaited<ReturnType<typeof readSubstitutionContext>> | null =
      null
    try {
      online = await readSubstitutionContext(this.#gameId, tenant)
    } catch {
      online = null
    }
    this.#assert()
    if (online) {
      if (online.generation !== r.grant.d4)
        throw new Error('記録権世代が開始資格と一致しません')
      const context = this.#contextValue(
        tenant,
        online.generation,
        online.state.away.teamId,
        online.state.home.teamId,
      )
      await r.contexts.save(context)
      this.#assert()
      this.#context = context
      return context
    }
    const stored = await r.contexts.read(tenant, this.#gameId)
    this.#assert()
    if (!stored || !isPlayerRegistrationContext(stored))
      throw new Error('登録の端末文脈がありません')
    if (stored.d4 !== r.grant.d4)
      throw new Error('登録の端末文脈が開始資格と一致しません')
    this.#context = stored
    return stored
  }

  #contextValue(
    tenantId: string,
    d4: string,
    awayTeamId: string,
    homeTeamId: string,
  ): PlayerRegistrationContext {
    return Object.freeze({
      tenantId,
      gameId: this.#gameId,
      d4,
      awayTeamId,
      homeTeamId,
    })
  }

  #registrationInput(slot: DurableQueueSlot) {
    const input = slot.event.fields.V7
    return isPlayerRegistrationInput(input) ? input : null
  }

  async #readViews(): Promise<readonly PlayerRegistrationView[]> {
    const r = this.#resources!
    const context = this.#context
    if (!context) return Object.freeze([])
    const views: PlayerRegistrationView[] = []
    let cursor: number | null = null
    do {
      const page = await r.queue.readSlotsPage(this.#scope(), cursor, 100)
      this.#assert()
      for (const slot of page.items) {
        if (slot.event.fields.V5 !== REGISTRATION_KIND_ID) continue
        const input = this.#registrationInput(slot)
        if (!input) continue
        const side =
          input.teamRecordId === context.awayTeamId
            ? 'away'
            : input.teamRecordId === context.homeTeamId
              ? 'home'
              : null
        if (!side) continue
        const mapping =
          typeof slot.d5 === 'string'
            ? await r.mappings.read(input.temporaryId)
            : undefined
        const state =
          slot.state === SYNCED
            ? mapping
              ? 'confirmed'
              : 'unconfirmed'
            : slot.state === EVACUATED
              ? 'evacuated'
              : slot.state === ACTION_REQUIRED
                ? 'action-required'
                : 'unsent'
        views.push(
          Object.freeze({
            temporaryId: input.temporaryId,
            name: input.name,
            side,
            d1: slot.d1,
            state,
            ...(mapping ? { officialId: mapping.officialId } : {}),
          }),
        )
      }
      cursor = page.nextCursorD1
    } while (cursor !== null)
    views.sort((first, second) => first.d1 - second.d1)
    return Object.freeze(views)
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
        (candidate) =>
          candidate.state === UNSENT || candidate.state === ACTION_REQUIRED,
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

  async #preparedView(): Promise<PlayerRegistrationView | null> {
    const prepared = await this.#prepared().catch(() => null)
    if (!prepared || prepared.event.fields.V5 !== REGISTRATION_KIND_ID)
      return null
    const input = prepared.event.fields.V7
    if (!isPlayerRegistrationInput(input)) return null
    const context = this.#context
    if (!context) return null
    const side =
      input.teamRecordId === context.awayTeamId
        ? 'away'
        : input.teamRecordId === context.homeTeamId
          ? 'home'
          : null
    if (!side) return null
    return Object.freeze({
      temporaryId: input.temporaryId,
      name: input.name,
      side,
      d1: prepared.d1,
      state: 'unsent',
    })
  }

  async #send(slot: DurableQueueSlot): Promise<PlayerRegistrationCommitResult> {
    this.#assert()
    const r = this.#resources!
    const input = this.#registrationInput(slot)
    if (!input || slot.state !== UNSENT || typeof slot.d5 !== 'string')
      return 'pending'
    const durable = await r.queue.readSlot(this.#scope(), slot.d1)
    this.#assert()
    if (!durable || !sameOrdinaryWire(durable.event, slot.event))
      return 'pending'
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
    if (!sameOrdinaryWire(original, playerRegistrationBody(durable, proof)))
      return 'blocked'
    const sent = await postPlayerRegistration(durable, proof, {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attempt.attemptId,
    })
    this.#assert()
    if (!sent.sent) {
      const status = sent.status
      if (
        status !== undefined &&
        status >= 400 &&
        status < 500 &&
        status !== 401 &&
        status !== 403 &&
        status !== 408 &&
        status !== 429
      )
        return 'blocked'
      return 'pending'
    }
    const parsed = readPlayerRegistrationAck(sent.response, {
      d4: r.grant.d4,
      d1: slot.d1,
      d5: slot.d5,
      temporaryId: input.temporaryId,
    })
    if (!parsed) return 'pending'
    const tenant = this.#identity.tenantId!
    const mapping: TemporaryPlayerMappingRecord = {
      temporaryId: parsed.mapping.temporaryId,
      officialId: parsed.mapping.officialId,
      tenantId: tenant,
      gameId: this.#gameId,
      d4: r.grant.d4,
      d5: slot.d5,
    }
    try {
      await r.mappings.append(mapping)
    } catch (error) {
      this.#assert()
      if (error instanceof TemporaryPlayerMappingConflictError) return 'blocked'
      return 'pending'
    }
    this.#assert()
    const applied = await applyAckToSlot(
      {
        scope: this.#scope(),
        d1: slot.d1,
        ack: parsed.ack,
        playerIdMappingTarget: {
          eventKind: PLAYER_REGISTRATION_KIND,
          event: durable.event,
          key: { d4: durable.d4, d1: durable.d1, d5: durable.d5 },
          temporaryId: input.temporaryId,
        },
      },
      r.queue,
    )
    this.#assert()
    return applied.outcome === 'applied' ? 'saved' : 'pending'
  }

  async #resumePrepared(): Promise<PlayerRegistrationCommitResult> {
    const prepared = await this.#prepared()
    if (!prepared) return 'ready'
    const r = this.#resources!
    if (prepared.event.fields.V5 !== REGISTRATION_KIND_ID) return 'pending'
    const proposed: DurableQueueSlot = {
      game: this.#gameId,
      d4: r.grant.d4,
      d1: prepared.d1,
      d5: prepared.d5,
      version: 1,
      event: prepared.event,
      state: UNSENT,
    }
    const original: unknown = JSON.parse(prepared.requestJson)
    if (
      !original ||
      typeof original !== 'object' ||
      !('recording_right_proof' in original)
    )
      return 'blocked'
    if (
      !sameOrdinaryWire(
        original,
        playerRegistrationBody(proposed, original.recording_right_proof),
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
    if (accepted.slot.d1 !== prepared.d1) return 'pending'
    return this.#send(accepted.slot)
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

  async load(): Promise<PlayerRegistrationPanelResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      await this.#readContext()
      const views = await this.#readViews()
      const prepared = await this.#preparedView()
      this.#views =
        prepared && !views.some((view) => view.d1 === prepared.d1)
          ? Object.freeze([...views, prepared])
          : views
      return this.#views.some(
        (view) =>
          view.state === 'unsent' ||
          view.state === 'action-required' ||
          view.state === 'unconfirmed',
      )
        ? 'pending'
        : 'ready'
    } catch {
      this.#views = Object.freeze([])
      return 'blocked'
    } finally {
      this.#busy = false
      this.#close()
    }
  }

  async register(
    draft: PlayerRegistrationDraft,
  ): Promise<PlayerRegistrationCommitResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    let accepted = false
    try {
      await this.#open()
      const context = this.#context ?? (await this.#readContext())
      const teamId =
        draft.side === 'away' ? context.awayTeamId : context.homeTeamId
      const proposedInput = registrationInputFromDraft(
        draft,
        teamId,
        crypto.randomUUID(),
      )
      if (!proposedInput) return 'invalid'
      const result = await runAsSingleWriter<PlayerRegistrationCommitResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const r = this.#resources!
          const prepared = await this.#prepared()
          if (prepared) return this.#resumePrepared()
          const next = await r.queue.readNextD1(this.#scope())
          if ((await r.queue.readSlot(this.#scope(), next)) !== undefined)
            return 'blocked'
          const d5 = crypto.randomUUID()
          const event = playerRegistrationEvent(
            this.#gameId,
            r.grant.d4,
            d5,
            proposedInput,
          )
          const proposed: DurableQueueSlot = {
            game: this.#gameId,
            d4: r.grant.d4,
            d1: next,
            d5,
            version: 1,
            event,
            state: UNSENT,
          }
          const body = playerRegistrationBody(
            proposed,
            r.grant.recording_right_proof,
          )
          await r.attempts.prepare({
            tenantId: this.#identity.tenantId!,
            gameId: this.#gameId,
            d4: r.grant.d4,
            d1: next,
            d5,
            body,
            event,
          })
          this.#assert()
          const queued = await appendPitchEventUnderLock(
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
          if (queued.outcome !== 'accepted')
            return queued.outcome === 'undetermined' ? 'pending' : 'blocked'
          accepted = true
          if (
            queued.slot.d1 !== next ||
            !sameOrdinaryWire(
              playerRegistrationBody(
                queued.slot,
                r.grant.recording_right_proof,
              ),
              body,
            )
          )
            return 'pending'
          // 追記順を送信順にする。古い未送信スロットがあれば登録は待つ。
          const oldest = await this.#oldest()
          this.#assert()
          if (!oldest) return 'pending'
          if (oldest.event.fields.V5 !== REGISTRATION_KIND_ID) return 'pending'
          return this.#send(oldest)
        },
        this.#injections(),
      )
      return result.recordingStarted ? result.value : 'blocked'
    } catch {
      return accepted ? 'pending' : 'blocked'
    } finally {
      this.#busy = false
      try {
        this.#views = this.#resources ? await this.#readViews() : this.#views
      } catch {
        /* 表示の再読取失敗は保存結果を変えない。 */
      }
      this.#close()
    }
  }

  async retry(): Promise<PlayerRegistrationCommitResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const result = await runAsSingleWriter<PlayerRegistrationCommitResult>(
        { gameIdentifier: this.#gameId },
        async () => {
          this.#assert()
          const slot = await this.#oldest()
          if (!slot) {
            return this.#resumePrepared()
          }
          if (slot.event.fields.V5 !== REGISTRATION_KIND_ID)
            return 'awaiting-substitution'
          if (slot.state !== UNSENT) return 'blocked'
          return this.#send(slot)
        },
        this.#injections(),
      )
      return result.recordingStarted ? result.value : 'blocked'
    } catch {
      return 'pending'
    } finally {
      this.#busy = false
      try {
        this.#views = this.#resources ? await this.#readViews() : this.#views
      } catch {
        /* 表示の再読取失敗は保存結果を変えない。 */
      }
      this.#close()
    }
  }

  #close(): void {
    if (this.#disposed && !this.#busy) {
      this.#resources?.queue.close()
      this.#resources?.attempts.close()
      this.#resources?.mappings.close()
      this.#resources?.contexts.close()
      this.#resources = null
      this.#context = null
    }
  }

  dispose(): void {
    this.#disposed = true
    this.#close()
  }
}

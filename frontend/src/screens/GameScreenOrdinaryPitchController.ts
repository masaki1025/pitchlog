import {
  formatFirstBallWire,
  type FirstBallPayload,
} from '../api/firstBallWire'
import type {
  StateSnapshot,
  T2NoEndCore,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import type { OrdinaryPrefixRef, OrdinaryNoEnd } from '../api/ordinaryPitchWire'
import {
  buildSyncEventRequestBody,
  postSyncEvents,
  type SyncEventSendRequest,
} from '../api/client.syncEvents'
import type { SyncRequestCredentials } from '../api/client'
import {
  formatOrdinaryPitchWire,
  isOrdinaryContinuationRequest,
  isOrdinaryContinuationSuccess,
  sameOrdinaryWire,
  readOrdinaryPitchAck,
  type OrdinaryPitchPayload,
} from '../api/ordinaryPitchWire'
import { nextOrdinaryD2 } from '../api/ordinaryAppendPolicy'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { FirstBallAttemptPersistence } from '../lib/firstBallAttemptPersistence'
import { OrdinaryPitchAttemptPersistence } from '../lib/ordinaryPitchAttemptPersistence'
import type {
  InitialDeviceEnrollmentResponse,
  InitialGameStartResponse,
} from '../api/gameStart'
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
import { PITCH_EVENT_KIND } from './GameScreenPitchEvent'
import { commitPitchEvent } from './GameScreenPitchCommit'
import { applyAckToSlot } from './GameScreenAckApplication'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import {
  prepareOrdinaryPitch,
  ordinaryPitchEvent,
  type OrdinaryRecordingContext,
  type OrdinaryScreenObservation,
  type PreparedOrdinaryPitch,
} from './GameScreenOrdinaryPitchProvider'
export type OrdinaryOperationResult = 'ready' | 'saved' | 'pending' | 'blocked'
type Resources = {
  queue: DurableQueue
  attempts: OrdinaryPitchAttemptPersistence
  device: InitialDeviceEnrollmentResponse
  grant: InitialGameStartResponse
}
const kinds = [PITCH_EVENT_KIND]
function sequence(v: string): number {
  if (
    !/^[1-9][0-9]*$/.test(v) ||
    v.trim() !== v ||
    BigInt(v) > BigInt(Number.MAX_SAFE_INTEGER)
  )
    throw new Error('通常投球の位置を確認できません')
  return Number(v)
}

/** 端末受理と送信を分け、同じ旧slotを同attemptのまま再送する。 */
export class GameScreenOrdinaryPitchController {
  #context: OrdinaryRecordingContext
  #identity: FirstBallIdentity
  #readIdentity: () => FirstBallIdentity
  #resources: Resources | null = null
  #writer: SingleWriterInjections
  #disposed = false
  #busy = false
  #opening: Promise<void> | null = null
  #head: number
  #canAppend = true
  #retryEvidenceUnavailable = false
  constructor(
    context: OrdinaryRecordingContext,
    readIdentity: () => FirstBallIdentity,
    writer: SingleWriterInjections = {},
  ) {
    this.#context = structuredClone(context)
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
    this.#writer = writer
    this.#head = sequence(context.nextPosition.d1)
  }
  get context(): OrdinaryRecordingContext {
    return structuredClone(this.#context)
  }
  get retryEvidenceUnavailable(): boolean {
    return this.#retryEvidenceUnavailable
  }
  get canAppend(): boolean {
    return (
      this.#canAppend &&
      !this.#disposed &&
      this.#current() &&
      this.#resources !== null
    )
  }
  #current(): boolean {
    const now = this.#readIdentity()
    return (
      !this.#disposed &&
      now.verified &&
      this.#identity.verified &&
      now.tenantId !== null &&
      now.tenantId === this.#identity.tenantId &&
      now.epoch === this.#identity.epoch &&
      now.tenantId === this.#context.prefixRef.tenantId
    )
  }
  #assert(): void {
    if (!this.#current()) throw new Error('通常投球の操作前提を確認できません')
  }
  #scope() {
    return { game: this.#context.game.id, d4: this.#context.game.current_d4 }
  }
  async #open(): Promise<void> {
    this.#assert()
    if (this.#opening) return this.#opening
    if (this.#resources) return
    this.#opening = (async () => {
      let store: GameStartPersistence | null = null,
        queue: DurableQueue | null = null,
        attempts: OrdinaryPitchAttemptPersistence | null = null
      try {
        store = await GameStartPersistence.open()
        const tenant = this.#identity.tenantId!,
          device = await store.readDevice(tenant),
          start = await store.readStart(tenant, this.#context.game.id)
        this.#assert()
        if (
          !device ||
          !start ||
          start.status !== 'received' ||
          !start.grant ||
          !this.#context.serverStamp ||
          start.grant.recovery_generation !==
            this.#context.serverStamp.recoveryGeneration ||
          device.device_id !== start.grant.device_id ||
          start.grant.d4 !== this.#context.game.current_d4 ||
          start.grant.away_lineup_id !==
            this.#context.game.lineups.away.lineup_id ||
          start.grant.home_lineup_id !==
            this.#context.game.lineups.home.lineup_id
        )
          throw new Error('開始資格を確認できません')
        queue = await openDurableQueue({
          databaseName: 'pitchlog-first-ball-queue-' + tenant,
        })
        attempts = await OrdinaryPitchAttemptPersistence.open()
        this.#assert()
        this.#resources = { queue, attempts, device, grant: start.grant }
        queue = null
        attempts = null
        const r = this.#resources,
          serverNext = this.#head,
          localNext = await r.queue.readNextD1(this.#scope())
        // D1 counter欠落をserver値へ飛ばして補修しない。
        if (localNext < serverNext) this.#canAppend = false
        this.#head = (await this.#oldestUnsettledD1()) ?? serverNext
        // 確認済server anchorから未送信suffixだけを順次検証。full historyとは呼ばない。
        for (let d1 = serverNext; d1 < localNext; d1++) {
          const slot = await r.queue.readSlot(this.#scope(), d1)
          this.#assert()
          if (!slot || !this.#restoreLocal(slot)) {
            this.#canAppend = false
            return
          }
        }
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
  /** server水位と各slotのA5を分け、最小未終結を主key有限ページで探す。 */
  async #oldestUnsettledD1(): Promise<number | null> {
    const queue = this.#resources!.queue
    let cursor: number | null = null
    do {
      const page = await queue.readSlotsPage(this.#scope(), cursor, 100)
      this.#assert()
      const open = page.items.find(
        (slot) =>
          slot.state === queueStateId('未送信') ||
          slot.state === queueStateId('要操作'),
      )
      if (open) return open.d1
      cursor = page.nextCursorD1
    } while (cursor !== null)
    return null
  }
  #advanceValues(
    prefixRef: OrdinaryPrefixRef,
    after: StateSnapshot,
    t2: OrdinaryNoEnd | T2NoEndCore,
    usedD2: string,
    slot: DurableQueueSlot,
  ): void {
    const next = nextOrdinaryD2(usedD2, this.#context.appendPolicy)
    const d1 = slot.d1 + 1
    if (!Number.isSafeInteger(d1) || next === null) this.#canAppend = false
    this.#context = {
      ...this.#context,
      prefixRef: structuredClone(prefixRef),
      after: structuredClone(after),
      t2: structuredClone(t2),
      priorKind: 'evaluated-prefix',
      source: 'local-provisional',
      nextPosition: { d1: String(d1), d2: next ?? usedD2 },
    }
  }
  #advance(prepared: PreparedOrdinaryPitch, slot: DurableQueueSlot): void {
    const value = prepared.payload.calculation.response.value
    this.#advanceValues(
      value.nextPrefixRef,
      value.t1.after,
      value.t2,
      prepared.nextPosition.d2,
      slot,
    )
  }
  #restoreLocal(slot: DurableQueueSlot): boolean {
    try {
      const legacy = slot.event.fields.V7 as FirstBallPayload
      if (legacy?.formatVersion === 'first-ball-play-v1') {
        if (
          legacy.calculation?.formatVersion !== 'first-ball-calculation-v1' ||
          legacy.calculation.artifactSha256 !== artifactIdentity.sha256 ||
          slot.d1 !== sequence(this.#context.nextPosition.d1) ||
          slot.event.fields.V6 !== sequence(this.#context.nextPosition.d2) ||
          slot.state === queueStateId('要操作') ||
          slot.state === queueStateId('退避済み') ||
          !sameOrdinaryWire(
            legacy.calculation.request.rules,
            this.#context.rules,
          ) ||
          !sameOrdinaryWire(
            legacy.calculation.request.t1.before,
            this.#context.after,
          )
        )
          return false
        const actual = {
          ok: true,
          value: invokeFirstBallDomain(
            'deriveFirstPitchWithContinuation',
            legacy.calculation.request,
          ),
        }
        if (!sameOrdinaryWire(actual, legacy.calculation.response)) return false
        const wire = formatFirstBallWire(
          legacy.calculation.request,
          legacy.calculation.response,
          legacy.observations,
          legacy.participants,
        )
        if (
          !sameOrdinaryWire(wire.payload, legacy) ||
          !sameOrdinaryWire(wire.stateDiff, slot.event.fields.V8)
        )
          return false
        const value = legacy.calculation.response.value
        this.#advanceValues(
          {
            ...this.#context.prefixRef,
            length: String(BigInt(this.#context.prefixRef.length) + 1n),
          },
          value.t1.after,
          value.t2,
          this.#context.nextPosition.d2,
          slot,
        )
        return true
      }
      const raw = slot.event.fields.V7 as OrdinaryPitchPayload
      if (
        raw?.formatVersion !== 'ordinary-pitch-play-v1' ||
        raw.calculation?.formatVersion !== 'ordinary-pitch-calculation-v1' ||
        raw.calculation.artifactSha256 !== artifactIdentity.sha256 ||
        !isOrdinaryContinuationRequest(raw.calculation.request) ||
        !isOrdinaryContinuationSuccess(raw.calculation.response) ||
        !sameOrdinaryWire(
          raw.calculation.request.prefixRef,
          this.#context.prefixRef,
        ) ||
        !sameOrdinaryWire(raw.calculation.request.rules, this.#context.rules) ||
        !sameOrdinaryWire(
          raw.calculation.request.t1.before,
          this.#context.after,
        ) ||
        slot.d1 !== sequence(this.#context.nextPosition.d1) ||
        slot.event.fields.V6 !== sequence(this.#context.nextPosition.d2) ||
        slot.state === queueStateId('要操作') ||
        slot.state === queueStateId('退避済み')
      )
        return false
      const actual = {
        ok: true,
        value: invokeFirstBallDomain(
          'deriveOrdinaryPitchWithContinuation',
          raw.calculation.request,
        ),
      }
      if (!sameOrdinaryWire(actual, raw.calculation.response)) return false
      const wire = formatOrdinaryPitchWire(
        raw.calculation.request,
        raw.calculation.response,
        raw.observations,
        raw.participants,
      )
      if (
        !sameOrdinaryWire(wire.payload, raw) ||
        !sameOrdinaryWire(wire.stateDiff, slot.event.fields.V8)
      )
        return false
      this.#advance(
        {
          ...wire,
          gameId: this.#context.game.id,
          d4: this.#context.game.current_d4,
          nextPosition: this.#context.nextPosition,
          source: 'local-provisional',
        },
        slot,
      )
      return true
    } catch {
      return false
    }
  }
  #writerInjections(): SingleWriterInjections {
    const original = this.#writer
    return {
      ...original,
      revalidateSingleWriter: async (context) => {
        if (
          !this.#current() ||
          !this.#resources ||
          context.gameIdentifier !== this.#context.game.id ||
          context.lockName !== singleWriterLockName(this.#context.game.id) ||
          context.lock === null ||
          typeof context.lock !== 'object' ||
          (await original.revalidateSingleWriter?.(context)) !== true
        )
          return false
        const next = await this.#resources.queue.readNextD1(this.#scope())
        return Number.isSafeInteger(next) && next >= 1 && this.#current()
      },
    }
  }
  async inspect(): Promise<OrdinaryOperationResult> {
    try {
      await this.#open()
      this.#assert()
      const slot = await this.#resources!.queue.readSlot(
        this.#scope(),
        this.#head,
      )
      return slot && slot.state !== queueStateId('同期済み')
        ? 'pending'
        : this.#canAppend
          ? 'ready'
          : 'blocked'
    } catch {
      return 'blocked'
    }
  }
  async #credentials(
    request: SyncEventSendRequest,
    mode: 'initial' | 'retry',
  ): Promise<SyncRequestCredentials> {
    this.#assert()
    const r = this.#resources!
    if (request.slots.length !== 1) throw new Error('単一要求ではありません')
    const slot = request.slots[0]!,
      body = buildSyncEventRequestBody(request)
    if (!('events' in body) || typeof slot.d5 !== 'string')
      throw new Error('要求識別を確認できません')
    let attemptId: string
    const payload = slot.event.fields.V7 as { formatVersion?: unknown } | null
    if (payload?.formatVersion === 'first-ball-play-v1') {
      // 結果不明の旧初球も既attemptを読むだけ。同slotを新D5/attemptへ置換しない。
      const legacy = await FirstBallAttemptPersistence.open()
      try {
        const old = await legacy.read(
          this.#identity.tenantId!,
          this.#context.game.id,
        )
        if (!old || old.d5 !== slot.d5)
          throw new Error('旧要求を確認できません')
        const events: unknown = JSON.parse(old.requestJson)
        if (!sameOrdinaryWire(events, body.events))
          throw new Error('旧要求内容が一致しません')
        attemptId = old.attemptId
      } finally {
        legacy.close()
      }
    } else {
      if (payload?.formatVersion !== 'ordinary-pitch-play-v1')
        throw new Error('要求形式を確認できません')
      const key = {
        tenantId: this.#identity.tenantId!,
        gameId: this.#context.game.id,
        d4: this.#context.game.current_d4,
        d1: slot.d1,
        d5: slot.d5,
      }
      const fixed =
        mode === 'initial'
          ? await r.attempts.prepare({ ...key, events: body.events })
          : await r.attempts.read(key)
      // 未送信stateだけではHTTP未到達を証明できない。retryでattemptを発行しない。
      if (
        !fixed ||
        !sameOrdinaryWire(JSON.parse(fixed.requestJson), body.events)
      )
        throw new Error('元要求の耐久attemptを確認できません')
      attemptId = fixed.attemptId
    }
    this.#assert()
    return {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attemptId,
    }
  }
  async submit(
    observation: OrdinaryScreenObservation,
    vocabulary: Readonly<{
      tenantId: string
      pitchTypeKeys: readonly string[]
    }>,
  ): Promise<OrdinaryOperationResult> {
    if (this.#busy || !this.#canAppend) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      this.#assert()
      if (!this.#canAppend) return 'blocked'
      const r = this.#resources!,
        prepared = prepareOrdinaryPitch(
          this.#context,
          observation,
          vocabulary,
          this.#identity.tenantId!,
        ),
        expected = sequence(prepared.nextPosition.d1),
        d5 = crypto.randomUUID()
      let key: { d4: string; d1: number; d5: string } | null = null
      const result = await commitPitchEvent(
        {
          gameIdentifier: this.#context.game.id,
          scope: this.#scope(),
          d5,
          version: 1,
          event: ordinaryPitchEvent(prepared, d5),
          recordingRightProof: r.grant.recording_right_proof,
          eventKinds: kinds,
        },
        {
          queue: r.queue,
          singleWriterInjections: this.#writerInjections(),
          beforeAppend: async () => {
            this.#assert()
            if (
              !this.#canAppend ||
              (await r.queue.readNextD1(this.#scope())) !== expected ||
              !sameOrdinaryWire(
                prepared.payload.calculation.request.prefixRef,
                this.#context.prefixRef,
              )
            )
              throw new Error('記録位置が変わりました')
          },
          prepareSend: async (request) => {
            const slot = request.slots[0]!
            key = { d4: this.#context.game.current_d4, d1: slot.d1, d5 }
            this.#advance(prepared, slot)
            const credentials = await this.#credentials(request, 'initial')
            this.#head = (await this.#oldestUnsettledD1()) ?? slot.d1
            if (slot.d1 !== this.#head)
              throw new Error('先行要求の終結を確認してください')
            return credentials
          },
          readAck: (value) =>
            this.#current() && key !== null
              ? readOrdinaryPitchAck(value, key)
              : undefined,
        },
      )
      this.#assert()
      if (
        result.outcome === 'attempted' &&
        result.ackApplication?.outcome === 'applied'
      ) {
        if (key !== null) this.#head = expected + 1
        return 'saved'
      }
      return (await r.queue.readSlot(this.#scope(), expected))
        ? 'pending'
        : 'blocked'
    } catch {
      return this.#context.source === 'local-provisional'
        ? 'pending'
        : 'blocked'
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }
  /** 同じslot/body/attemptだけを送る。新規D1/D5は作らない。 */
  async retry(): Promise<OrdinaryOperationResult> {
    if (this.#busy) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      const r = this.#resources!
      this.#assert()
      const result = await runAsSingleWriter<OrdinaryOperationResult>(
        { gameIdentifier: this.#context.game.id },
        async () => {
          this.#assert()
          const first = await this.#oldestUnsettledD1()
          if (first === null) return this.#canAppend ? 'ready' : 'blocked'
          this.#head = first
          const slot = await r.queue.readSlot(this.#scope(), first)
          if (!slot) return this.#canAppend ? 'ready' : 'blocked'
          if (
            slot.state !== queueStateId('未送信') ||
            typeof slot.d5 !== 'string'
          )
            return 'pending'
          const request: SyncEventSendRequest = {
            gameId: this.#context.game.id,
            recordingRightProof: r.grant.recording_right_proof,
            slots: [slot],
            eventKinds: kinds,
          }
          let credentials: SyncRequestCredentials
          try {
            credentials = await this.#credentials(request, 'retry')
          } catch {
            this.#retryEvidenceUnavailable = true
            return 'blocked'
          }
          this.#retryEvidenceUnavailable = false
          this.#assert()
          const sent = await postSyncEvents({
            ...request,
            syncCredentials: credentials,
          })
          if (!sent.sent) return 'pending'
          this.#assert()
          const ack = readOrdinaryPitchAck(sent.response, {
              d4: this.#context.game.current_d4,
              d1: slot.d1,
              d5: slot.d5,
            }),
            applied = await applyAckToSlot(
              { scope: this.#scope(), d1: slot.d1, ack },
              r.queue,
            )
          this.#assert()
          if (applied.outcome !== 'applied') return 'pending'
          this.#head = slot.d1 + 1
          return 'saved'
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

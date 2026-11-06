import {
  formatLineupPrefixWire,
  isLineupDefinition,
} from '../api/lineupPrefixWire'
import type {
  LineupPlayPrefixV7,
  NonplayNormalV7,
} from '../../../contracts/state-transition/lineup_play_prefix_payload_v1'
import {
  isLineupRecordingContext,
  prepareLineupPrefix,
  lineupPrefixEvent,
  type PreparedLineupPrefix,
} from './GameScreenOrdinaryPitchProvider'
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
import { formatTerminalPitchWire } from '../api/terminalPitchWire'
import type { PlayPrefixV7 } from '../api/terminalPitchWire'
import { nextOrdinaryD2 } from '../api/ordinaryAppendPolicy'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { FirstBallAttemptPersistence } from '../lib/firstBallAttemptPersistence'
import { OrdinaryPitchAttemptPersistence } from '../lib/ordinaryPitchAttemptPersistence'
import {
  OrdinaryPreparedEnvelopePersistence,
  type PreparedEnvelope,
} from '../lib/ordinaryPreparedEnvelopePersistence'
import type { LocalAcceptanceBoundary } from '../lib/localRecordingScope'
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
  type SingleWriterRevalidationContext,
} from '../lib/sync/singleWriter'
import { queueStateId } from '../lib/sync/queueState'
import { PITCH_EVENT_KIND } from './GameScreenPitchEvent'
import { commitPitchEvent } from './GameScreenPitchCommit'
import { appendPitchEventUnderLock } from './GameScreenPitchAcceptance'
import { applyAckToSlot } from './GameScreenAckApplication'
import { withNonBlockingSingleWriter } from './GameScreenSingleWriter'
import type { FirstBallIdentity } from './GameScreenFirstBallController'
import {
  prepareOrdinaryPitch,
  ordinaryPitchEvent,
  type OrdinaryScreenObservation,
  type PreparedOrdinaryPitch,
  type RecordingContext,
  type PlayScreenObservation,
  type PreparedPlayPrefix,
  isPlayRecordingContext,
  preparePlayPrefix,
  playPrefixEvent,
} from './GameScreenOrdinaryPitchProvider'
/** 旧画面は旧v3計算だけを扱う。NPを旧Source/物理CPへ変換しない。 */
function isLegacyLineupPayload(
  value: LineupPlayPrefixV7,
): value is Exclude<LineupPlayPrefixV7, NonplayNormalV7> {
  return value.calculation.formatVersion === 'play-prefix-calculation-v3'
}
export type OrdinaryOperationResult = 'ready' | 'saved' | 'pending' | 'blocked'
export type LocalOrdinaryResult = 'queued-local' | 'pending' | 'blocked'
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
  #context: RecordingContext
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
  #localBoundary: LocalAcceptanceBoundary | null
  #localAcceptanceActive = false
  constructor(
    context: RecordingContext,
    readIdentity: () => FirstBallIdentity,
    writer: SingleWriterInjections = {},
    localBoundary: LocalAcceptanceBoundary | null = null,
  ) {
    this.#context = structuredClone(context)
    if (
      isLineupRecordingContext(context) &&
      context.lineupSource.kind === 'locked-prefix-v3'
    )
      this.#canAppend = false
    this.#readIdentity = readIdentity
    this.#identity = { ...readIdentity() }
    this.#writer = writer
    this.#localBoundary = localBoundary
    this.#head = sequence(context.nextPosition.d1)
  }
  get context(): RecordingContext {
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
  /** local表示の入口用。実際の受理資格は毎回withinAcceptance内で判定する。 */
  get canAppendLocal(): boolean {
    return this.#localBoundary !== null && this.#canAppend && !this.#disposed
  }
  #current(): boolean {
    const now = this.#readIdentity()
    const local = this.#localBoundary !== null
    return (
      !this.#disposed &&
      (local
        ? this.#localAcceptanceActive &&
          !now.verified &&
          !this.#identity.verified
        : now.verified && this.#identity.verified) &&
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
          if (!slot || !(await this.#restoreLocal(slot))) {
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
    if (
      isPlayRecordingContext(this.#context) ||
      isLineupRecordingContext(this.#context)
    )
      throw new Error('旧記録からの接続を確認してください')
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
  #advance(
    prepared: PreparedOrdinaryPitch | PreparedPlayPrefix | PreparedLineupPrefix,
    slot: DurableQueueSlot,
  ): void {
    if (prepared.payload.formatVersion === 'play-prefix-play-v3') {
      if (
        !isLineupRecordingContext(this.#context) ||
        !isLegacyLineupPayload(prepared.payload)
      )
        throw new Error('記録形式が一致しません')
      const r = prepared.payload.calculation.response.value,
        q = prepared.payload.calculation.request
      const d1 = slot.d1 + 1,
        d2 = nextOrdinaryD2(
          prepared.nextPosition.d2,
          this.#context.appendPolicy,
        )
      if (
        !Number.isSafeInteger(d1) ||
        d2 === null ||
        r.t2.decision.lockFurtherPlayInput ||
        r.t2.tiebreakStartRequired
      )
        this.#canAppend = false
      const nextPosition = {
        d1: String(d1),
        d2: d2 ?? prepared.nextPosition.d2,
      }
      this.#context = {
        ...this.#context,
        prefixRef: r.nextPrefixRef,
        after: r.t1.after,
        t2: r.t2,
        nextPosition,
        source: 'local-provisional',
        lineupSource: {
          ...q.source,
          kind:
            r.t2.decision.lockFurtherPlayInput || r.t2.tiebreakStartRequired
              ? 'locked-prefix-v3'
              : 'evaluated-prefix-v3',
          prefixRef: r.nextPrefixRef,
          after: r.t1.after,
          t2: r.t2,
          historyDepth: r.nextPrefixRef.length,
          playCount: r.nextPrefixRef.length,
          lastSource: r.playIdentity,
          position: { ...nextPosition, appliedWatermark: String(slot.d1) },
          priorArtifactSha256: r.executionArtifactSha256,
          runners: r.runners,
          participants: r.participants,
          lineup: r.lineup,
          rosterDigest: r.rosterDigest,
          responsibility: r.nextResponsibility,
          provenance: {
            kind: 'confirmed-prefix',
            checkpoint: r.nextPrefixRef.checkpoint,
            sourceIdentity: r.playIdentity,
            historyDepth: r.nextPrefixRef.length,
          },
        },
      }
      return
    }
    if (prepared.payload.formatVersion === 'play-prefix-play-v2') {
      if (!isPlayRecordingContext(this.#context))
        throw new Error('記録形式が一致しません')
      const r = prepared.payload.calculation.response.value,
        q = prepared.payload.calculation.request
      const d1 = slot.d1 + 1,
        d2 = nextOrdinaryD2(
          prepared.nextPosition.d2,
          this.#context.appendPolicy,
        )
      if (!Number.isSafeInteger(d1) || d2 === null) this.#canAppend = false
      const nextPosition = {
        d1: String(d1),
        d2: d2 ?? prepared.nextPosition.d2,
      }
      this.#context = {
        ...this.#context,
        prefixRef: r.nextPrefixRef,
        after: r.t1.after,
        t2: r.t2,
        nextPosition,
        source: 'local-provisional',
        playSource: {
          ...q.source,
          kind: 'evaluated-prefix-v2',
          prefixRef: r.nextPrefixRef,
          after: r.t1.after,
          t2: r.t2,
          historyDepth: r.nextPrefixRef.length,
          playCount: r.nextPrefixRef.length,
          lastSource: q.playIdentity,
          position: { ...nextPosition, appliedWatermark: String(slot.d1) },
          priorArtifactSha256: r.executionArtifactSha256,
          runners: r.runners,
          participants: r.participants,
          nextBatter: null,
          bridge: null,
          responsibility: {
            ...q.source.responsibility,
            paStartSource: r.t1.plateAppearanceEnded
              ? { kind: 'confirmed-play', id: q.playIdentity.eventId }
              : q.source.responsibility.paStartSource,
          },
        },
      }
      return
    }
    const value = prepared.payload.calculation.response.value
    this.#advanceValues(
      value.nextPrefixRef,
      value.t1.after,
      value.t2,
      prepared.nextPosition.d2,
      slot,
    )
  }
  async #restoreLocal(slot: DurableQueueSlot): Promise<boolean> {
    try {
      const play = slot.event.fields.V7 as PlayPrefixV7 | LineupPlayPrefixV7
      if (play?.formatVersion === 'play-prefix-play-v3') {
        if (!isLegacyLineupPayload(play)) return false
        if (
          !isLineupRecordingContext(this.#context) ||
          !isLineupDefinition(play.calculation.request, 'Request') ||
          !isLineupDefinition(play.calculation.response, 'Success') ||
          !sameOrdinaryWire(
            play.calculation.request.prefixRef,
            this.#context.prefixRef,
          ) ||
          !sameOrdinaryWire(
            play.calculation.request.source,
            this.#context.lineupSource,
          ) ||
          !sameOrdinaryWire(
            play.calculation.request.rules,
            this.#context.rules,
          ) ||
          !sameOrdinaryWire(
            play.calculation.request.t1.before,
            this.#context.after,
          )
        )
          return false
        const payload = play,
          q = payload.calculation.request
        if (
          q.playIdentity.d5 !== slot.d5 ||
          q.prefixRef.gameId !== this.#context.game.id ||
          q.prefixRef.tenantId !== this.#identity.tenantId ||
          slot.event.fields.V6 !== sequence(this.#context.nextPosition.d2) ||
          slot.state === queueStateId('要操作') ||
          slot.state === queueStateId('退避済み')
        )
          return false
        const actual = {
          ok: true as const,
          value: invokeFirstBallDomain(
            'deriveLineupPlayPrefixWithContinuation',
            q,
          ) as typeof payload.calculation.response.value,
        }
        if (!sameOrdinaryWire(actual, payload.calculation.response))
          return false
        const wire = await formatLineupPrefixWire(
          q,
          actual,
          payload.observations,
          payload.participants,
        )
        if (
          !sameOrdinaryWire(wire.payload, payload) ||
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
      }
      if (play?.formatVersion === 'play-prefix-play-v2') {
        if (
          !isPlayRecordingContext(this.#context) ||
          !play.calculation ||
          play.calculation.formatVersion !== 'play-prefix-calculation-v2' ||
          play.calculation.artifactSha256 !== artifactIdentity.sha256 ||
          slot.d1 !== sequence(this.#context.nextPosition.d1) ||
          slot.event.fields.V6 !== sequence(this.#context.nextPosition.d2) ||
          slot.d5 !== play.calculation.request.playIdentity.d5 ||
          slot.state === queueStateId('要操作') ||
          slot.state === queueStateId('退避済み')
        )
          return false
        const q = play.calculation.request
        if (
          !sameOrdinaryWire(q.prefixRef, this.#context.prefixRef) ||
          !sameOrdinaryWire(q.rules, this.#context.rules) ||
          !sameOrdinaryWire(q.t1.before, this.#context.after) ||
          !sameOrdinaryWire(
            { ...q.source, nextBatter: null },
            this.#context.playSource,
          )
        )
          return false
        const actual = {
          ok: true as const,
          value: invokeFirstBallDomain(
            'derivePlayPrefixWithContinuation',
            q,
          ) as PlayPrefixV7['calculation']['response']['value'],
        }
        if (!sameOrdinaryWire(actual, play.calculation.response)) return false
        const wire = await formatTerminalPitchWire(
          q,
          actual,
          play.observations,
          play.participants,
        )
        if (
          !sameOrdinaryWire(wire.payload, play) ||
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
      }
      // 未確認v1 suffixへprivate bridgeを創作しない。元slotの再送は別経路で可能。
      if (
        isPlayRecordingContext(this.#context) ||
        isLineupRecordingContext(this.#context)
      )
        return false
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
    if (this.#localBoundary) return 'blocked'
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
      if (
        payload?.formatVersion !== 'ordinary-pitch-play-v1' &&
        payload?.formatVersion !== 'play-prefix-play-v2' &&
        payload?.formatVersion !== 'play-prefix-play-v3'
      )
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
      if (mode === 'retry' && payload.formatVersion === 'play-prefix-play-v3') {
        // local受理はV12を含む本文全体を固定済み。復帰後も置換せず照合する。
        const envelopes = await OrdinaryPreparedEnvelopePersistence.open()
        try {
          const prepared = await envelopes.read(key)
          if (
            prepared &&
            (prepared.d5 !== slot.d5 ||
              prepared.attemptId !== attemptId ||
              !sameOrdinaryWire(prepared.event, slot.event) ||
              !sameOrdinaryWire(prepared.requestBody, body))
          )
            throw new Error('端末準備済み原文が一致しません')
        } finally {
          envelopes.close()
        }
      }
    }
    this.#assert()
    return {
      deviceId: r.device.device_id,
      deviceCredential: r.device.device_credential,
      attempt: attemptId,
    }
  }
  async submit(
    observation: PlayScreenObservation,
    vocabulary: Readonly<{
      tenantId: string
      pitchTypeKeys: readonly string[]
    }>,
  ): Promise<OrdinaryOperationResult> {
    if (this.#localBoundary) return 'blocked'
    if (this.#busy || !this.#canAppend) return 'blocked'
    this.#busy = true
    try {
      await this.#open()
      this.#assert()
      if (!this.#canAppend) return 'blocked'
      const r = this.#resources!,
        d5 = crypto.randomUUID()
      const prepared = isLineupRecordingContext(this.#context)
        ? await prepareLineupPrefix(
            this.#context,
            observation,
            vocabulary,
            this.#identity.tenantId!,
            { d5, eventId: crypto.randomUUID(), playId: crypto.randomUUID() },
            crypto.randomUUID(),
          )
        : isPlayRecordingContext(this.#context)
          ? await preparePlayPrefix(
              this.#context,
              observation,
              vocabulary,
              this.#identity.tenantId!,
              { d5, eventId: crypto.randomUUID(), playId: crypto.randomUUID() },
              crypto.randomUUID(),
            )
          : prepareOrdinaryPitch(
              this.#context,
              observation as OrdinaryScreenObservation,
              vocabulary,
              this.#identity.tenantId!,
            )
      this.#assert()
      const expected = sequence(prepared.nextPosition.d1)
      let key: { d4: string; d1: number; d5: string } | null = null
      const result = await commitPitchEvent(
        {
          gameIdentifier: this.#context.game.id,
          scope: this.#scope(),
          d5,
          version: 1,
          event:
            prepared.payload.formatVersion === 'play-prefix-play-v3'
              ? lineupPrefixEvent(prepared as PreparedLineupPrefix, d5)
              : prepared.payload.formatVersion === 'play-prefix-play-v2'
                ? playPrefixEvent(prepared as PreparedPlayPrefix, d5)
                : ordinaryPitchEvent(prepared as PreparedOrdinaryPitch, d5),
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
  /** 同ゲーム排他と読取専用auth lease内で原文を先に耐久固定し、HTTPなしでE0追記する。 */
  async localEnqueue(
    observation: PlayScreenObservation,
    vocabulary: Readonly<{
      tenantId: string
      pitchTypeKeys: readonly string[]
    }>,
  ): Promise<LocalOrdinaryResult> {
    if (!this.#localBoundary || this.#busy || this.#disposed) return 'blocked'
    this.#busy = true
    let appendStarted = false
    let accepted = false
    try {
      let held: SingleWriterRevalidationContext | null = null
      const injection = withNonBlockingSingleWriter(this.#writer)
      const started = await runAsSingleWriter<LocalOrdinaryResult>(
        { gameIdentifier: this.#context.game.id },
        async () => {
          if (held === null) return 'blocked'
          return this.#localBoundary!.withinAcceptance(held, async () => {
            this.#localAcceptanceActive = true
            let envelopes: OrdinaryPreparedEnvelopePersistence | null = null
            try {
              this.#assert()
              await this.#open()
              this.#assert()
              if (!this.#canAppend || !isLineupRecordingContext(this.#context))
                return 'blocked'
              const r = this.#resources!
              const expected = sequence(this.#context.nextPosition.d1)
              const scope = this.#scope()
              if (
                (await r.queue.readNextD1(scope)) !== expected ||
                (await r.queue.readSlot(scope, expected)) !== undefined
              )
                return 'blocked'
              this.#assert()
              envelopes = await OrdinaryPreparedEnvelopePersistence.open()
              const key = {
                tenantId: this.#identity.tenantId!,
                gameId: this.#context.game.id,
                d4: this.#context.game.current_d4,
                d1: expected,
              }
              const prior = await envelopes.read(key)
              this.#assert()
              if (
                prior &&
                (!sameOrdinaryWire(prior.observation, observation) ||
                  !sameOrdinaryWire(prior.vocabulary, vocabulary))
              )
                return 'blocked'
              let d5: string
              let eventId: string
              let playId: string
              let checkpointId: string
              let attemptId: string
              if (prior) {
                const payload = prior.event.fields.V7 as LineupPlayPrefixV7
                if (
                  !isLegacyLineupPayload(payload) ||
                  !isLineupDefinition(payload.calculation.request, 'Request') ||
                  !isLineupDefinition(payload.calculation.response, 'Success')
                )
                  return 'blocked'
                const request = payload.calculation.request
                d5 = prior.d5
                eventId = request.playIdentity.eventId
                playId = request.playIdentity.playId
                checkpointId = request.nextCheckpoint.id
                attemptId = prior.attemptId
              } else {
                d5 = crypto.randomUUID()
                eventId = crypto.randomUUID()
                playId = crypto.randomUUID()
                checkpointId = crypto.randomUUID()
                attemptId = crypto.randomUUID()
              }
              const prepared = await prepareLineupPrefix(
                this.#context,
                observation,
                vocabulary,
                this.#identity.tenantId!,
                { d5, eventId, playId },
                checkpointId,
              )
              this.#assert()
              const event = lineupPrefixEvent(prepared, d5)
              const provisional: DurableQueueSlot = {
                game: scope.game,
                d4: scope.d4,
                d1: expected,
                d5,
                version: 1,
                event,
                state: queueStateId('未送信'),
              }
              const body = buildSyncEventRequestBody({
                gameId: this.#context.game.id,
                recordingRightProof: r.grant.recording_right_proof,
                slots: [provisional],
                eventKinds: kinds,
              })
              if ('sent' in body) return 'blocked'
              const candidate: PreparedEnvelope = {
                schemaVersion: 1,
                ...key,
                d5,
                attemptId,
                observation: structuredClone(observation),
                vocabulary: structuredClone(vocabulary),
                event: structuredClone(event),
                requestBody: structuredClone(body),
              }
              if (prior && !sameOrdinaryWire(prior, candidate)) return 'blocked'
              const fixed = await envelopes.save(candidate)
              this.#assert()
              if (!sameOrdinaryWire(fixed, candidate)) return 'blocked'
              const attempt = await r.attempts.prepare(
                { ...key, d5, events: body.events },
                attemptId,
              )
              this.#assert()
              if (
                attempt.attemptId !== attemptId ||
                !sameOrdinaryWire(
                  JSON.parse(attempt.requestJson),
                  body.events,
                ) ||
                (await r.queue.readNextD1(scope)) !== expected ||
                (await r.queue.readSlot(scope, expected)) !== undefined
              )
                return 'blocked'
              this.#assert()
              appendStarted = true
              const result = await appendPitchEventUnderLock(
                {
                  gameIdentifier: this.#context.game.id,
                  scope,
                  d5,
                  version: 1,
                  event,
                },
                r.queue,
              )
              this.#assert()
              if (
                result.outcome !== 'accepted' ||
                result.slot.d1 !== expected ||
                !sameOrdinaryWire(result.slot.event, event) ||
                result.slot.state !== queueStateId('未送信')
              ) {
                if (
                  result.outcome === 'undetermined' ||
                  result.outcome === 'accepted'
                )
                  this.#canAppend = false
                return result.outcome === 'not-accepted' ? 'blocked' : 'pending'
              }
              if (!(await this.#restoreLocal(result.slot))) {
                this.#canAppend = false
                return 'pending'
              }
              this.#assert()
              accepted = true
              return 'queued-local'
            } finally {
              envelopes?.close()
              this.#localAcceptanceActive = false
            }
          })
        },
        {
          ...injection,
          revalidateSingleWriter: async (context) => {
            const allowed = await injection.revalidateSingleWriter?.(context)
            if (allowed === true) held = context
            return allowed
          },
        },
      )
      return started.recordingStarted ? started.value : 'blocked'
    } catch {
      // E0後の結果不明は既slotを保持し、次の独立操作を止める。
      if (appendStarted || accepted) this.#canAppend = false
      return appendStarted ? 'pending' : 'blocked'
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }
  /** cold reload時の未送信suffix復元。local資格境界の外で旧slotを採用しない。 */
  async inspectLocal(): Promise<OrdinaryOperationResult> {
    if (!this.#localBoundary || this.#busy || this.#disposed) return 'blocked'
    this.#busy = true
    try {
      let held: SingleWriterRevalidationContext | null = null
      const injection = withNonBlockingSingleWriter(this.#writer)
      const started = await runAsSingleWriter<OrdinaryOperationResult>(
        { gameIdentifier: this.#context.game.id },
        async () => {
          if (held === null) return 'blocked'
          return this.#localBoundary!.withinAcceptance(held, async () => {
            this.#localAcceptanceActive = true
            try {
              this.#assert()
              await this.#open()
              this.#assert()
              if (!this.#canAppend || !isLineupRecordingContext(this.#context))
                return 'blocked'
              return (await this.#oldestUnsettledD1()) === null
                ? 'ready'
                : 'pending'
            } finally {
              this.#localAcceptanceActive = false
            }
          })
        },
        {
          ...injection,
          revalidateSingleWriter: async (context) => {
            const allowed = await injection.revalidateSingleWriter?.(context)
            if (allowed === true) held = context
            return allowed
          },
        },
      )
      return started.recordingStarted ? started.value : 'blocked'
    } catch {
      return 'blocked'
    } finally {
      this.#busy = false
      this.#closeIfDisposed()
    }
  }
  /** 同じslot/body/attemptだけを送る。新規D1/D5は作らない。 */
  async retry(): Promise<OrdinaryOperationResult> {
    if (this.#localBoundary) return 'blocked'
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

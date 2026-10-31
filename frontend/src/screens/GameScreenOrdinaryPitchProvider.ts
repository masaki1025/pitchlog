import type {
  Source,
  PrefixRef,
  PlayRequest,
  PlaySuccess,
  NextBatter,
  Snapshot,
  PlayIdentity,
} from '../../../contracts/state-transition/play_prefix_v2'
import {
  isPlayPrefixGame,
  type PlayPrefixGame,
} from '../api/recordedPrefixGame'
import {
  formatTerminalPitchWire,
  sealPlayMetadata,
  playHash,
  isPlayDefinition,
} from '../api/terminalPitchWire'
import artifactIdentity from '../../public/domain/pitchlog-domain.json'

import {
  isOrdinaryAppendPolicy,
  type OrdinaryAppendPolicy,
} from '../api/ordinaryAppendPolicy'
import geometry from '../../../contracts/display_geometry_263_v1.json'
import type {
  SavedRuleWire,
  StateSnapshot,
  T2NoEndCore,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import {
  STARTED_GAME_BASE_KEYS,
  type StartedGameMetadata,
} from '../api/startedGame'
import {
  isStartedGameMetadata,
  isStartedGameStateSnapshot,
} from '../api/startedGame'
import type { FirstBallObservations } from '../api/firstBallWire'
import { canonicalUuid } from '../api/authIntent'
import {
  formatOrdinaryPitchWire,
  isOrdinaryPrefixRef,
  isOrdinarySavedRules,
  sameOrdinaryWire,
  type OrdinaryPrefixRef,
  type OrdinaryNoEnd,
  type OrdinaryResultId,
  type OrdinaryContinuationRequest,
  type OrdinaryContinuationSuccess,
  type OrdinaryPreparedWire,
  OrdinaryPitchWireError,
} from '../api/ordinaryPitchWire'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import type { SyncEvent } from '../lib/sync/syncEvent'

export type OrdinaryRecordingContext = Readonly<{
  /** 読取codecが検査した開始metadata。stateは開始snapshot、afterが現在値。 */
  game: StartedGameMetadata
  /** 実read DTOから画面が束縛するserver anchor。数学の成功はこの供給を代替しない。 */
  serverStamp?: Readonly<{
    recoveryGeneration: string
    checkpointAnchor: Readonly<{
      id: string
      revision: string
      history_version: string
    }> | null
    lastSavedAt: string
  }>
  prefixRef: OrdinaryPrefixRef
  rules: SavedRuleWire
  after: StateSnapshot
  t2: OrdinaryNoEnd | T2NoEndCore | null
  priorKind: 'started-initial' | 'evaluated-prefix'
  /** サーバー原本、又は確定queueからの別軸。prefix長から採番しない。 */
  nextPosition: Readonly<{ d1: string; d2: string }>
  appendPolicy: OrdinaryAppendPolicy
  source: 'server-confirmed' | 'local-provisional'
}>
export type OrdinaryScreenObservation = Readonly<{
  resultId: OrdinaryResultId
  pitchTypeKey: string
  screenX: number
  screenY: number
  view: 'catcher' | 'pitcher'
  pitchSpeed: FirstBallObservations['pitchSpeed']
  stance: FirstBallObservations['stance']
  battingSide: FirstBallObservations['battingSide']
}>
export type PreparedOrdinaryPitch = OrdinaryPreparedWire &
  Readonly<{
    gameId: string
    d4: string
    nextPosition: OrdinaryRecordingContext['nextPosition']
    source: OrdinaryRecordingContext['source']
  }>
function invalid(): never {
  throw new OrdinaryPitchWireError()
}
function sequence(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^[1-9][0-9]*$/.test(value) &&
    value.trim() === value &&
    BigInt(value) <= BigInt(Number.MAX_SAFE_INTEGER)
  )
}
/** サーバー原値又は自己の耐久queue由来のcontextだけから、単一artifactを呼ぶ。 */
export function prepareOrdinaryPitch(
  context: OrdinaryRecordingContext,
  observation: OrdinaryScreenObservation,
  vocabulary: Readonly<{ tenantId: string; pitchTypeKeys: readonly string[] }>,
  expectedTenantId: string,
): PreparedOrdinaryPitch {
  const game = context.game
  if (
    !isStartedGameMetadata(game) ||
    !isOrdinaryAppendPolicy(context.appendPolicy) ||
    !isStartedGameStateSnapshot(context.after) ||
    !isOrdinaryPrefixRef(context.prefixRef) ||
    !isOrdinarySavedRules(context.rules) ||
    context.prefixRef.gameId !== game.id ||
    context.prefixRef.generation !== game.current_d4 ||
    context.prefixRef.tenantId !== expectedTenantId ||
    vocabulary.tenantId !== expectedTenantId ||
    !canonicalUuid.test(expectedTenantId) ||
    !Array.isArray(vocabulary.pitchTypeKeys) ||
    !vocabulary.pitchTypeKeys.includes(observation.pitchTypeKey) ||
    !Number.isFinite(observation.screenX) ||
    !Number.isFinite(observation.screenY) ||
    !sequence(context.nextPosition.d1) ||
    !sequence(context.nextPosition.d2) ||
    !['server-confirmed', 'local-provisional'].includes(context.source)
  )
    return invalid()
  const {
    batterId,
    pitcherId,
    catcherId,
    battingOrder: order,
  } = selectPitchParticipants(game, context.after)
  const request: OrdinaryContinuationRequest = {
    version: '1',
    prefixRef: structuredClone(context.prefixRef),
    rules: structuredClone(context.rules),
    t1: {
      eventKind: 'batting-result',
      resultId: observation.resultId,
      pitchEventKind: 'pitch-event',
      before: structuredClone(context.after),
    },
    prior: {
      kind: context.priorKind,
      prefixRef: structuredClone(context.prefixRef),
      rules: structuredClone(context.rules),
      after: structuredClone(context.after),
      t2: structuredClone(context.t2),
    },
  }
  const course = invokeFirstBallDomain('quantizeCourse', {
    x: String(observation.screenX),
    y: String(observation.screenY),
    view: observation.view,
    size: String(geometry.size),
  }) as FirstBallObservations['course']
  const computed = {
    ok: true,
    value: invokeFirstBallDomain(
      'deriveOrdinaryPitchWithContinuation',
      request,
    ),
  } as OrdinaryContinuationSuccess
  const wire = formatOrdinaryPitchWire(
    request,
    computed,
    {
      pitchTypeKey: observation.pitchTypeKey,
      course,
      pitchSpeed: observation.pitchSpeed,
      stance: observation.stance,
      battingSide: observation.battingSide,
    },
    { batterId, pitcherId, catcherId, battingOrder: order },
  )
  return {
    ...wire,
    gameId: game.id,
    d4: game.current_d4,
    nextPosition: structuredClone(context.nextPosition),
    source: context.source,
  }
}
/** D1はqueue側で採番し、D2は確認済みの別軸位置をそのまま運ぶ。 */
export function ordinaryPitchEvent(
  prepared: PreparedOrdinaryPitch,
  d5: string,
): SyncEvent {
  if (
    typeof d5 !== 'string' ||
    d5.length !== 36 ||
    !canonicalUuid.test(d5) ||
    !sequence(prepared.nextPosition.d2)
  )
    return invalid()
  return {
    fields: {
      V1: d5,
      V3: prepared.d4,
      V4: prepared.gameId,
      V5: '1',
      V6: Number(prepared.nextPosition.d2),
      V7: structuredClone(prepared.payload),
      V8: structuredClone(prepared.stateDiff),
    },
  }
}

export type PlayRecordingContext = Omit<
  OrdinaryRecordingContext,
  'prefixRef' | 'after' | 't2' | 'priorKind'
> &
  Readonly<{
    mode: 'play-prefix-v2'
    prefixRef: PrefixRef
    after: Snapshot
    t2: Source['t2']
    playSource: Source
  }>
export type RecordingContext = OrdinaryRecordingContext | PlayRecordingContext
export function isPlayRecordingContext(
  c: RecordingContext,
): c is PlayRecordingContext {
  return 'mode' in c && c.mode === 'play-prefix-v2'
}
export type PlayScreenObservation = Omit<
  OrdinaryScreenObservation,
  'resultId'
> &
  Readonly<{
    resultId:
      OrdinaryResultId | 'batting-result.walk' | 'batting-result.hit-by-pitch'
    nextBatter?: NextBatter | null
  }>
/** 同じ保存roster/lineup照合を旧v1とv2で共有する。 */
export function selectPitchParticipants(
  game: StartedGameMetadata,
  after: StateSnapshot | Snapshot,
) {
  const half = after.stateFields['state.half'],
    order = after.stateFields['state.battingOrder']
  const attacking = half === 'top' ? 'away' : 'home',
    defending = half === 'top' ? 'home' : 'away'
  const away = game.roster.teams[0],
    home = game.roster.teams[1]
  if (
    away.side !== 'away' ||
    home.side !== 'home' ||
    away.team_id !== game.away_team_record_id ||
    home.team_id !== game.home_team_record_id ||
    game.lineups.away.team_record_id !== away.team_id ||
    game.lineups.home.team_record_id !== home.team_id
  )
    return invalid()
  const attackRoster = attacking === 'away' ? away : home,
    defendRoster = defending === 'away' ? away : home
  const batters = attackRoster.participants.filter(
    (p) => p.batting_slot.kind === 'slot' && p.batting_slot.slot === order,
  )
  const atPosition = (position: '1' | '2') =>
    defendRoster.participants.filter((p) =>
      p.roles.some((r) => r.kind === 'fielding' && r.position === position),
    )
  const pitchers = atPosition('1'),
    catchers = atPosition('2')
  if (batters.length !== 1 || pitchers.length !== 1 || catchers.length !== 1)
    return invalid()
  const batterId = batters[0]!.player.player_id,
    pitcherId = pitchers[0]!.player.player_id,
    catcherId = catchers[0]!.player.player_id
  const attackLineup = game.lineups[attacking].entries.filter(
    (p) => p.batting_order === order,
  )
  const defender = (position: '1' | '2') =>
    game.lineups[defending].entries.filter(
      (p) =>
        p.fielding_position.kind === 'fielding' &&
        p.fielding_position.position === position,
    )
  const pitcher = defender('1'),
    catcher = defender('2')
  if (
    attackLineup.length !== 1 ||
    attackLineup[0]!.player_id !== batterId ||
    pitcher.length !== 1 ||
    pitcher[0]!.player_id !== pitcherId ||
    catcher.length !== 1 ||
    catcher[0]!.player_id !== catcherId
  )
    return invalid()
  return {
    batterId,
    pitcherId,
    catcherId,
    battingOrder: order as '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9',
  }
}
/** 移行は実GETの証拠を提案へ写すだけで、資格はサーバーが再照合する。 */
export async function playContextFromRead(
  value: PlayPrefixGame,
  tenantId: string,
): Promise<PlayRecordingContext> {
  if (!isPlayPrefixGame(value) || value.prefix_ref.tenantId !== tenantId)
    return invalid()
  // 基本metadataのfield集合は既codecの正本から取得する。
  const metadata = Object.fromEntries(
    STARTED_GAME_BASE_KEYS.filter((k) => k !== 'read_kind').map((k) => [
      k,
      value[k],
    ]),
  ) as StartedGameMetadata
  if (!isStartedGameMetadata(metadata)) return invalid()
  const rulesDigest = await playHash(value.rules),
    layoutDigest = await playHash(value.roster)
  const origin =
    value.prefix_ref.version === '1'
      ? value.prefix_ref
      : value.prefix_ref.origin
  const ref: PrefixRef =
    value.prefix_ref.version === '2'
      ? value.prefix_ref
      : {
          version: '2',
          scope: 'play-prefix-v2',
          tenantId,
          gameId: value.id,
          generation: value.current_d4,
          length: origin.length,
          checkpoint: value.bridge_checkpoint!,
          historyVersion: '1',
          origin,
        }
  const bridge =
    value.prefix_ref.version === '1'
      ? {
          kind:
            BigInt(origin.length) === 0n
              ? ('started-initial' as const)
              : ('ordinary-only-confirmed' as const),
          v1Ref: origin,
          ordinaryPlayCount: origin.length,
          allPlayCount: origin.length,
          historyDepth: origin.length,
          lastSource: value.last_source,
          priorArtifactSha256: value.prior_artifact_sha256,
          rulesDigest,
          layoutDigest,
          checkpoint: ref.checkpoint,
        }
      : null
  const people =
    value.participants ?? selectPitchParticipants(metadata, value.after)
  const source: Source = {
    kind: bridge ? 'bridged-v1' : 'evaluated-prefix-v2',
    prefixRef: ref,
    rules: value.rules,
    after: value.after,
    t2: value.t2,
    historyDepth: ref.length,
    playCount: ref.length,
    lastSource: value.last_source,
    position: {
      d1: value.next_position.d1,
      d2: value.next_position.d2,
      appliedWatermark: String(BigInt(value.next_position.d1) - 1n),
    },
    priorArtifactSha256: value.prior_artifact_sha256,
    executionArtifactSha256: artifactIdentity.sha256,
    rulesDigest,
    layoutDigest,
    runners: value.runners,
    participants: {
      batterId: people.batterId,
      pitcherId: people.pitcherId,
      battingOrder: people.battingOrder,
    },
    nextBatter: null,
    bridge,
    responsibility: {
      kind: 'no-change',
      paStartSource: value.pa_start_source,
      previousPitcherId: null,
      strikesAtChange: null,
      ballsAtChange: null,
    },
  }
  if (!isPlayDefinition(source, 'Source')) return invalid()
  return structuredClone({
    mode: 'play-prefix-v2',
    game: metadata,
    serverStamp: {
      recoveryGeneration: value.recovery_generation,
      checkpointAnchor: value.checkpoint_anchor,
      lastSavedAt: value.last_saved_at,
    },
    prefixRef: ref,
    rules: value.rules,
    after: value.after,
    t2: value.t2,
    playSource: source,
    nextPosition: value.next_position,
    appendPolicy: value.append_policy,
    source: 'server-confirmed',
  })
}
/** IDは耐久slotに固定する一回の予約。状態計算は配布artifactへ一回だけ渡す。 */
export async function preparePlayPrefix(
  context: PlayRecordingContext,
  observation: PlayScreenObservation,
  vocabulary: Readonly<{ tenantId: string; pitchTypeKeys: readonly string[] }>,
  tenantId: string,
  playIdentity: PlayIdentity,
  checkpointId: string,
) {
  if (
    context.prefixRef.tenantId !== tenantId ||
    vocabulary.tenantId !== tenantId ||
    !vocabulary.pitchTypeKeys.includes(observation.pitchTypeKey) ||
    !Number.isFinite(observation.screenX) ||
    !Number.isFinite(observation.screenY) ||
    !isStartedGameMetadata(context.game)
  )
    return invalid()
  const participants = selectPitchParticipants(context.game, context.after)
  if (
    !sameOrdinaryWire(
      {
        batterId: participants.batterId,
        pitcherId: participants.pitcherId,
        battingOrder: participants.battingOrder,
      },
      context.playSource.participants,
    )
  )
    return invalid()
  const terminal =
    observation.resultId === 'batting-result.walk' ||
    observation.resultId === 'batting-result.hit-by-pitch'
  const nextBatter = terminal ? (observation.nextBatter ?? null) : null
  if (terminal) {
    const team = context.game.roster.teams.find(
      (t) =>
        t.side ===
        (context.after.stateFields['state.half'] === 'top' ? 'away' : 'home'),
    )
    if (
      !nextBatter ||
      !team ||
      !team.participants.some(
        (p) =>
          p.player.player_id === nextBatter.batterId &&
          p.batting_slot.kind === 'slot' &&
          p.batting_slot.slot === nextBatter.battingOrder,
      )
    )
      return invalid()
  }
  const request: PlayRequest = {
    version: '2',
    prefixRef: context.prefixRef,
    rules: context.rules,
    t1: {
      eventKind: 'batting-result',
      resultId: observation.resultId,
      pitchEventKind: 'pitch-event',
      before: context.after,
    },
    source: { ...context.playSource, nextBatter },
    playIdentity,
    nextCheckpoint: {
      id: checkpointId,
      revision: String(BigInt(context.prefixRef.checkpoint.revision) + 1n),
      digest: '0'.repeat(64),
    },
  }
  const course = invokeFirstBallDomain('quantizeCourse', {
    x: String(observation.screenX),
    y: String(observation.screenY),
    view: observation.view,
    size: String(geometry.size),
  }) as FirstBallObservations['course']
  const response: PlaySuccess = {
    ok: true,
    value: invokeFirstBallDomain(
      'derivePlayPrefixWithContinuation',
      request,
    ) as PlaySuccess['value'],
  }
  const sealed = await sealPlayMetadata(request, response)
  const wire = await formatTerminalPitchWire(
    sealed.request,
    sealed.response,
    {
      pitchTypeKey: observation.pitchTypeKey,
      course,
      pitchSpeed: observation.pitchSpeed,
      stance: observation.stance,
      battingSide: observation.battingSide,
    },
    participants,
  )
  return {
    ...wire,
    gameId: context.game.id,
    d4: context.game.current_d4,
    nextPosition: context.nextPosition,
    source: context.source,
  }
}
export type PreparedPlayPrefix = Awaited<ReturnType<typeof preparePlayPrefix>>
export function playPrefixEvent(
  prepared: PreparedPlayPrefix,
  d5: string,
): SyncEvent {
  if (
    d5 !== prepared.payload.calculation.request.playIdentity.d5 ||
    !sequence(prepared.nextPosition.d2)
  )
    return invalid()
  return {
    fields: {
      V1: d5,
      V3: prepared.d4,
      V4: prepared.gameId,
      V5: '1',
      V6: Number(prepared.nextPosition.d2),
      V7: structuredClone(prepared.payload),
      V8: structuredClone(prepared.stateDiff),
    },
  }
}

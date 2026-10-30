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
import type { StartedGameMetadata } from '../api/startedGame'
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
  const half = context.after.stateFields['state.half'],
    order = context.after.stateFields['state.battingOrder']
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

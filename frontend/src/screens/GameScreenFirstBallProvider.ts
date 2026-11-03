import type {
  CombinedRequest,
  CombinedSuccess,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import geometry from '../../../contracts/display_geometry_263_v1.json'
import {
  formatFirstBallWire,
  FirstBallWireError,
  type FirstBallObservations,
  type FirstBallPreparedWire,
} from '../api/firstBallWire'
import { isStartedGame, type StartedGame } from '../api/startedGame'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { canonicalUuid } from '../api/authIntent'
import type { SyncEvent } from '../lib/sync/syncEvent'

export type FirstBallScreenObservation = Readonly<{
  resultId: 'batting-result.ball'
  pitchTypeKey: string
  screenX: number
  screenY: number
  view: 'catcher' | 'pitcher'
  pitchSpeed: FirstBallObservations['pitchSpeed']
  stance: FirstBallObservations['stance']
  battingSide: FirstBallObservations['battingSide']
}>
export type FirstBallVocabulary = Readonly<{
  tenantId: string
  pitchTypeKeys: readonly string[]
}>
export type PreparedFirstBall = FirstBallPreparedWire &
  Readonly<{ gameId: string; d4: string }>
function invalid(): never {
  throw new FirstBallWireError()
}

/** 保存済みinitialと実画面の観測だけを合成する。権利・資格・queueは扱わない。 */
export function prepareFirstBall(
  game: StartedGame,
  observation: FirstBallScreenObservation,
  vocabulary: FirstBallVocabulary,
  expectedTenantId: string,
): PreparedFirstBall {
  if (
    !isStartedGame(game) ||
    observation.resultId !== 'batting-result.ball' ||
    vocabulary.tenantId.length !== 36 ||
    !canonicalUuid.test(vocabulary.tenantId) ||
    vocabulary.tenantId !== expectedTenantId ||
    !Array.isArray(vocabulary.pitchTypeKeys) ||
    !vocabulary.pitchTypeKeys.includes(observation.pitchTypeKey) ||
    !Number.isFinite(observation.screenX) ||
    !Number.isFinite(observation.screenY)
  )
    return invalid()
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
  // 名簿配置の実参照を抜くだけで、打順や守備の計算を再実装しない。
  const batters = away.participants.filter(
    (p) => p.batting_slot.kind === 'slot' && p.batting_slot.slot === '1',
  )
  const pitchers = home.participants.filter((p) =>
    p.roles.some((r) => r.kind === 'fielding' && r.position === '1'),
  )
  const catchers = home.participants.filter((p) =>
    p.roles.some((r) => r.kind === 'fielding' && r.position === '2'),
  )
  if (batters.length !== 1 || pitchers.length !== 1 || catchers.length !== 1)
    return invalid()
  const batter = batters[0]!,
    pitcher = pitchers[0]!,
    catcher = catchers[0]!
  const batterId = batter.player.player_id,
    pitcherId = pitcher.player.player_id,
    catcherId = catcher.player.player_id
  const battersInLineup = game.lineups.away.entries.filter(
    (p) => p.batting_order === '1',
  )
  const position = (pos: '1' | '2') =>
    game.lineups.home.entries.filter(
      (p) =>
        p.fielding_position.kind === 'fielding' &&
        p.fielding_position.position === pos,
    )
  const pitcherInLineup = position('1'),
    catcherInLineup = position('2')
  if (
    battersInLineup.length !== 1 ||
    battersInLineup[0]!.player_id !== batterId ||
    pitcherInLineup.length !== 1 ||
    pitcherInLineup[0]!.player_id !== pitcherId ||
    catcherInLineup.length !== 1 ||
    catcherInLineup[0]!.player_id !== catcherId
  )
    return invalid()
  const r = game.applied_rules
  const request: CombinedRequest = {
    t1: {
      eventKind: 'batting-result',
      resultId: observation.resultId,
      pitchEventKind: 'pitch-event',
      before: structuredClone(game.state),
    },
    rules: {
      regulationInnings: String(r.regulationInnings),
      coldConditions: r.coldConditions.map((c) => ({
        pointDifference: String(c.pointDifference),
        startInning: String(c.startInning),
      })),
      extensionLimit:
        r.extensionLimit === null ? null : String(r.extensionLimit),
      tiebreak:
        r.tiebreak === null
          ? null
          : {
              startInning: String(r.tiebreak.startInning),
              runnerPlacement: r.tiebreak.runnerPlacement,
              leadoffRule: r.tiebreak.leadoffRule,
            },
      dh: r.dh,
    },
  }
  const course = invokeFirstBallDomain('quantizeCourse', {
    x: String(observation.screenX),
    y: String(observation.screenY),
    view: observation.view,
    size: String(geometry.size),
  }) as FirstBallObservations['course']
  const computed: CombinedSuccess = {
    ok: true,
    value: invokeFirstBallDomain(
      'deriveFirstPitchWithContinuation',
      request,
    ) as CombinedSuccess['value'],
  }
  const wire = formatFirstBallWire(
    request,
    computed,
    {
      pitchTypeKey: observation.pitchTypeKey,
      course,
      pitchSpeed: observation.pitchSpeed,
      stance: observation.stance,
      battingSide: observation.battingSide,
    },
    { batterId, pitcherId, catcherId, battingOrder: '1' },
  )
  return { ...wire, gameId: game.id, d4: game.current_d4 }
}

/** D1採番前の既スロット形へ写す。D2は初期状態の先頭論理位置1だけを受ける。 */
export function firstBallEvent(
  prepared: PreparedFirstBall,
  identity: Readonly<{ d5: string; d2: 1 }>,
): SyncEvent {
  if (
    typeof identity.d5 !== 'string' ||
    identity.d5.length !== 36 ||
    !canonicalUuid.test(identity.d5) ||
    identity.d2 !== 1
  )
    return invalid()
  return {
    fields: {
      V1: identity.d5,
      V3: prepared.d4,
      V4: prepared.gameId,
      V5: '1',
      V6: identity.d2,
      V7: structuredClone(prepared.payload),
      V8: structuredClone(prepared.stateDiff),
    },
  }
}

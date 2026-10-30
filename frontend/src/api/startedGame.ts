import type {
  FieldingRoleWire,
  OneToNineDecimal,
  ProjectionWire,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import type {
  StateSnapshot,
  T1Value,
  T2NoEndCore,
} from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
import { canonicalUuid } from './authIntent'
import { ApiError, apiRequest } from './client'
import type { PreparingGame } from './games'

type AppliedRules = Readonly<{
  ruleSetId: string
  regulationInnings: number
  coldConditions: readonly Readonly<{
    pointDifference: number
    startInning: number
  }>[]
  extensionLimit: number | null
  tiebreak: Readonly<{
    startInning: number
    runnerPlacement: string
    leadoffRule: string
  }> | null
  dh: boolean
}>
export type StartedLineup = Readonly<{
  lineup_id: string
  team_record_id: string
  entries: readonly Readonly<{
    player_id: string
    batting_order: OneToNineDecimal | null
    fielding_position: FieldingRoleWire
    uniform_number_snapshot: string | null
  }>[]
}>
export interface StartedGame extends Omit<
  PreparingGame,
  'status' | 'applied_rules'
> {
  read_kind: 'initial'
  status: 'in_progress'
  started_at: string
  applied_rules: AppliedRules
  lineups: Readonly<{ away: StartedLineup; home: StartedLineup }>
  roster: ProjectionWire
  state: StateSnapshot
  current_d4: string
}
/** 保存初球1行の公開値。物理41列のうち36列（座標2列はcourse 1値へ統合）。 */
export type StartedPlayRow = Readonly<{
  id: string
  game_id: string
  source_event_id: string
  play_number: 1
  batting_order: 1
  batter_id: string
  pitcher_id: string
  catcher_id: string
  batting_side: '右' | '左' | null
  stance: string | null
  strategy_key: string | null
  strategy_detail_key: string | null
  strategy_result_key: string | null
  batter_status: string | null
  event_kind: 'pitch'
  course: Readonly<{ unit: '1/263'; x: string; y: string }>
  pitch_type_key: string
  batting_result_key: string
  secondary_batting_result_key: string | null
  raw_fielder_position: string | null
  resolved_fielder_id: string | null
  batted_ball_type: string | null
  batted_ball_strength: string | null
  hit_x: number | null
  hit_y: number | null
  pickoff_type: string | null
  pickoff_detail: string | null
  error_type: string | null
  raw_error_position: string | null
  resolved_error_player_id: string | null
  pitch_speed: number | null
  press: '0' | '1プレス' | '3プレス' | '両プレス' | null
  fake_run: '0' | '1プレス' | '3プレス' | '両プレス' | null
  comment: string | null
  version: 1
}>
export type StartedStatFlags = T1Value['statFlags']
export type StartedHistoryEntry = T1Value['historyContext'][number]
/** 記録後（保存済みの先頭1球）の応答。`state` の意味はinitialと同じbefore。 */
export interface StartedRecordedGame extends Omit<StartedGame, 'read_kind'> {
  read_kind: 'recorded'
  after: StateSnapshot
  history: readonly StartedHistoryEntry[]
  stat_flags: StartedStatFlags
  t2: T2NoEndCore
  play_rows: readonly StartedPlayRow[]
}
export type StartedGameRead = StartedGame | StartedRecordedGame
export type StartedGameResult =
  | { kind: 'found'; game: StartedGameRead }
  | { kind: 'not-found' }
  | { kind: 'recorded-unavailable' }

type ObjectValue = Record<string, unknown>
function object(value: unknown): value is ObjectValue {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function exact(value: unknown, keys: readonly string[]): value is ObjectValue {
  return (
    object(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  )
}
function uuid(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.length === 36 &&
    canonicalUuid.test(value)
  )
}
function decimal(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    /^(?:0|[1-9][0-9]*)$/.test(value)
  )
}
function oneToNine(value: unknown): value is OneToNineDecimal {
  return (
    typeof value === 'string' && value.length === 1 && /^[1-9]$/.test(value)
  )
}
function timestamp(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(
      value,
    ) &&
    Number.isFinite(Date.parse(value))
  )
}
function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string'
}
function role(value: unknown): value is FieldingRoleWire {
  return (
    (exact(value, ['kind', 'position']) &&
      value.kind === 'fielding' &&
      oneToNine(value.position)) ||
    (exact(value, ['kind']) && value.kind === 'designated-hitter')
  )
}
function nineOrTen(value: unknown): value is unknown[] {
  return Array.isArray(value) && (value.length === 9 || value.length === 10)
}
function lineup(value: unknown): value is StartedLineup {
  return (
    exact(value, ['lineup_id', 'team_record_id', 'entries']) &&
    uuid(value.lineup_id) &&
    uuid(value.team_record_id) &&
    nineOrTen(value.entries) &&
    value.entries.every(
      (entry) =>
        exact(entry, [
          'player_id',
          'batting_order',
          'fielding_position',
          'uniform_number_snapshot',
        ]) &&
        uuid(entry.player_id) &&
        (entry.batting_order === null || oneToNine(entry.batting_order)) &&
        role(entry.fielding_position) &&
        nullableString(entry.uniform_number_snapshot),
    )
  )
}
function roster(value: unknown): value is ProjectionWire {
  return (
    exact(value, ['teams']) &&
    Array.isArray(value.teams) &&
    value.teams.length === 2 &&
    value.teams.every(
      (team, index) =>
        exact(team, ['team_id', 'side', 'participants']) &&
        uuid(team.team_id) &&
        team.side === (index === 0 ? 'away' : 'home') &&
        nineOrTen(team.participants) &&
        team.participants.every(
          (entry) =>
            exact(entry, ['player', 'batting_slot', 'roles', 'entry_origin']) &&
            exact(entry.player, ['kind', 'player_id']) &&
            entry.player.kind === 'official' &&
            uuid(entry.player.player_id) &&
            ((exact(entry.batting_slot, ['kind']) &&
              entry.batting_slot.kind === 'none') ||
              (exact(entry.batting_slot, ['kind', 'slot']) &&
                entry.batting_slot.kind === 'slot' &&
                oneToNine(entry.batting_slot.slot))) &&
            Array.isArray(entry.roles) &&
            entry.roles.length === 1 &&
            role(entry.roles[0]) &&
            exact(entry.entry_origin, ['kind']) &&
            entry.entry_origin.kind === 'initial',
        ),
    )
  )
}
function score(value: unknown): boolean {
  return (
    exact(value, ['home', 'away']) && decimal(value.home) && decimal(value.away)
  )
}
function state(value: unknown): value is StateSnapshot {
  if (!exact(value, ['stateFields', 'scoreboard'])) return false
  const fields = value.stateFields
  const board = value.scoreboard
  return (
    exact(fields, [
      'state.half',
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.runners',
      'state.battingOrder',
      'state.tiebreakActive',
      'state.gameEnded',
      'state.inning',
      'state.score',
    ]) &&
    (fields['state.half'] === 'top' || fields['state.half'] === 'bottom') &&
    [
      'state.count.strikes',
      'state.count.balls',
      'state.outs',
      'state.battingOrder',
      'state.inning',
    ].every((key) => decimal(fields[key])) &&
    typeof fields['state.runners'] === 'string' &&
    [
      'empty',
      'first',
      'second',
      'third',
      'first-second',
      'first-third',
      'second-third',
      'loaded',
    ].includes(fields['state.runners']) &&
    typeof fields['state.tiebreakActive'] === 'boolean' &&
    typeof fields['state.gameEnded'] === 'boolean' &&
    score(fields['state.score']) &&
    exact(board, ['inningScores', 'hits', 'errors', 'strikeouts', 'walks']) &&
    score(board.inningScores) &&
    ['hits', 'errors', 'strikeouts', 'walks'].every((key) =>
      decimal(board[key]),
    )
  )
}
function integer(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value)
}
function rules(value: unknown): value is AppliedRules {
  return (
    exact(value, [
      'ruleSetId',
      'regulationInnings',
      'coldConditions',
      'extensionLimit',
      'tiebreak',
      'dh',
    ]) &&
    uuid(value.ruleSetId) &&
    integer(value.regulationInnings) &&
    Array.isArray(value.coldConditions) &&
    value.coldConditions.every(
      (tier) =>
        exact(tier, ['pointDifference', 'startInning']) &&
        integer(tier.pointDifference) &&
        integer(tier.startInning),
    ) &&
    (value.extensionLimit === null || integer(value.extensionLimit)) &&
    (value.tiebreak === null ||
      (exact(value.tiebreak, [
        'startInning',
        'runnerPlacement',
        'leadoffRule',
      ]) &&
        integer(value.tiebreak.startInning) &&
        typeof value.tiebreak.runnerPlacement === 'string' &&
        typeof value.tiebreak.leadoffRule === 'string')) &&
    typeof value.dh === 'boolean'
  )
}
const INITIAL_KEYS = [
  'read_kind',
  'id',
  'scheduled_at',
  'game_type_key',
  'tournament_key',
  'away_team_record_id',
  'home_team_record_id',
  'plate_umpire',
  'section_label',
  'week_label',
  'day_label',
  'game_number_label',
  'status',
  'started_at',
  'applied_rules',
  'lineups',
  'roster',
  'state',
  'current_d4',
] as const
const RECORDED_KEYS = [
  ...INITIAL_KEYS,
  'after',
  'history',
  'stat_flags',
  't2',
  'play_rows',
] as const
const PRESS_STATES = ['0', '1プレス', '3プレス', '両プレス'] as const
const STAT_FLAG_KEYS = [
  '投球回算入アウト',
  '投球数',
  '奪三振',
  '与四球',
  '与死球',
  '被安打',
  '被本塁打',
  '失点',
  '失策',
  '打席',
  '打数',
  '安打',
  '本塁打',
  '塁打',
  '犠打',
  '犠飛',
  '四球',
  '死球',
  '三振',
  '打撃妨害出塁',
  '走塁妨害出塁',
  '得点',
  '打点',
] as const
const PLAY_ROW_KEYS = [
  'id',
  'game_id',
  'source_event_id',
  'play_number',
  'batting_order',
  'batter_id',
  'pitcher_id',
  'catcher_id',
  'batting_side',
  'stance',
  'strategy_key',
  'strategy_detail_key',
  'strategy_result_key',
  'batter_status',
  'event_kind',
  'course',
  'pitch_type_key',
  'batting_result_key',
  'secondary_batting_result_key',
  'raw_fielder_position',
  'resolved_fielder_id',
  'batted_ball_type',
  'batted_ball_strength',
  'hit_x',
  'hit_y',
  'pickoff_type',
  'pickoff_detail',
  'error_type',
  'raw_error_position',
  'resolved_error_player_id',
  'pitch_speed',
  'press',
  'fake_run',
  'comment',
  'version',
] as const
function finiteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}
function unitNumber(value: unknown): value is number {
  return finiteNumber(value) && value >= 0 && value <= 1
}
function nullableAny<T>(
  check: (value: unknown) => value is T,
): (value: unknown) => value is T | null {
  return (value): value is T | null => value === null || check(value)
}
function pressState(
  value: unknown,
): value is (typeof PRESS_STATES)[number] | null {
  return (
    value === null ||
    (typeof value === 'string' &&
      (PRESS_STATES as readonly string[]).includes(value))
  )
}
function course(value: unknown): value is StartedPlayRow['course'] {
  return (
    exact(value, ['unit', 'x', 'y']) &&
    value.unit === '1/263' &&
    decimal(value.x) &&
    decimal(value.y) &&
    BigInt(value.x) <= 263n &&
    BigInt(value.y) <= 263n
  )
}
function ordinaryPlayRow(value: unknown): value is RecordedPrefixPlayRow {
  return (
    exact(value, PLAY_ROW_KEYS) &&
    uuid(value.id) &&
    uuid(value.game_id) &&
    uuid(value.source_event_id) &&
    integer(value.play_number) &&
    value.play_number >= 1 &&
    integer(value.batting_order) &&
    value.batting_order >= 1 &&
    value.batting_order <= 9 &&
    value.version === 1 &&
    uuid(value.batter_id) &&
    uuid(value.pitcher_id) &&
    uuid(value.catcher_id) &&
    (value.batting_side === null ||
      value.batting_side === '右' ||
      value.batting_side === '左') &&
    value.event_kind === 'pitch' &&
    course(value.course) &&
    typeof value.pitch_type_key === 'string' &&
    value.pitch_type_key.length > 0 &&
    typeof value.batting_result_key === 'string' &&
    value.batting_result_key.length > 0 &&
    nullableString(value.stance) &&
    nullableString(value.strategy_key) &&
    nullableString(value.strategy_detail_key) &&
    nullableString(value.strategy_result_key) &&
    nullableString(value.batter_status) &&
    nullableString(value.secondary_batting_result_key) &&
    nullableString(value.raw_fielder_position) &&
    nullableString(value.resolved_fielder_id) &&
    nullableString(value.batted_ball_type) &&
    nullableString(value.batted_ball_strength) &&
    nullableAny(unitNumber)(value.hit_x) &&
    nullableAny(unitNumber)(value.hit_y) &&
    nullableString(value.pickoff_type) &&
    nullableString(value.pickoff_detail) &&
    nullableString(value.error_type) &&
    nullableString(value.raw_error_position) &&
    nullableString(value.resolved_error_player_id) &&
    nullableAny(finiteNumber)(value.pitch_speed) &&
    pressState(value.press) &&
    pressState(value.fake_run) &&
    nullableString(value.comment)
  )
}
function playRow(value: unknown): value is StartedPlayRow {
  return (
    ordinaryPlayRow(value) &&
    value.play_number === 1 &&
    value.batting_order === 1
  )
}
function statFlags(value: unknown): value is StartedStatFlags {
  return (
    exact(value, STAT_FLAG_KEYS) &&
    STAT_FLAG_KEYS.every((key) => typeof value[key] === 'boolean')
  )
}
function historyEntry(value: unknown): value is StartedHistoryEntry {
  if (!exact(value, ['kind', 'difference']) || value.kind !== 'confirmed-play')
    return false
  const difference = value.difference
  if (!exact(difference, ['stateFields', 'scoreboard', 'statFlags']))
    return false
  // 初球は常に ball なので、差分は balls の before/after 1件だけである。
  const fields = difference.stateFields
  if (!exact(fields, ['state.count.balls'])) return false
  const balls = fields['state.count.balls']
  if (
    !exact(balls, ['before', 'after']) ||
    !decimal(balls.before) ||
    !decimal(balls.after)
  )
    return false
  return exact(difference.scoreboard, []) && statFlags(difference.statFlags)
}
function t2(value: unknown): value is T2NoEndCore {
  if (!exact(value, ['kind', 'evaluation_point', 'basis'])) return false
  if (
    value.kind !== 'evaluated-no-end-condition' ||
    value.evaluation_point !== 'post-play'
  )
    return false
  const basis = value.basis
  if (!exact(basis, ['regulation', 'cold', 'extra_and_draw', 'walk_off']))
    return false
  const regulation = basis.regulation
  const cold = basis.cold
  const extra = basis.extra_and_draw
  const walkOff = basis.walk_off
  return (
    exact(regulation, [
      'kind',
      'regulation_innings',
      'observed_inning',
      'observed_half',
    ]) &&
    regulation.kind === 'before-regulation-completion' &&
    (regulation.regulation_innings === '7' ||
      regulation.regulation_innings === '9') &&
    decimal(regulation.observed_inning) &&
    (regulation.observed_half === 'top' ||
      regulation.observed_half === 'bottom') &&
    exact(cold, ['kind']) &&
    cold.kind === 'no-configured-cold-condition' &&
    exact(extra, ['kind', 'configured_extension_limit']) &&
    extra.kind === 'before-extra-inning-boundary' &&
    (extra.configured_extension_limit === null ||
      decimal(extra.configured_extension_limit)) &&
    exact(walkOff, ['kind']) &&
    walkOff.kind === 'top-half-without-score-change'
  )
}
/** initial と recorded で共通の確定状態を検証する（read_kindは呼出側）。 */
function confirmedState(value: ObjectValue): boolean {
  return (
    value.status === 'in_progress' &&
    uuid(value.id) &&
    uuid(value.away_team_record_id) &&
    uuid(value.home_team_record_id) &&
    timestamp(value.scheduled_at) &&
    timestamp(value.started_at) &&
    typeof value.game_type_key === 'string' &&
    [
      'game_official',
      'game_semi_official',
      'game_open',
      'game_intrasquad',
      'game_other',
    ].includes(value.game_type_key) &&
    typeof value.tournament_key === 'string' &&
    value.tournament_key.length > 0 &&
    [
      'plate_umpire',
      'section_label',
      'week_label',
      'day_label',
      'game_number_label',
    ].every((key) => nullableString(value[key])) &&
    rules(value.applied_rules) &&
    exact(value.lineups, ['away', 'home']) &&
    lineup(value.lineups.away) &&
    lineup(value.lineups.home) &&
    roster(value.roster) &&
    state(value.state) &&
    typeof value.current_d4 === 'string' &&
    value.current_d4.length === 60 &&
    /^d4\.1\.[A-Za-z0-9_-]{55}$/.test(value.current_d4)
  )
}
/** transportの閉じた形だけを検証する。計算・権利・Readyを判定しない。 */
export function isStartedGame(value: unknown): value is StartedGame {
  return (
    exact(value, INITIAL_KEYS) &&
    value.read_kind === 'initial' &&
    confirmedState(value)
  )
}
/** 記録後の保存初球1件の閉じた形だけを検証する（再計算しない）。 */
export function isStartedRecordedGame(
  value: unknown,
): value is StartedRecordedGame {
  return (
    exact(value, RECORDED_KEYS) &&
    value.read_kind === 'recorded' &&
    confirmedState(value) &&
    state(value.after) &&
    Array.isArray(value.history) &&
    value.history.length === 1 &&
    historyEntry(value.history[0]) &&
    statFlags(value.stat_flags) &&
    t2(value.t2) &&
    Array.isArray(value.play_rows) &&
    value.play_rows.length === 1 &&
    playRow(value.play_rows[0]) &&
    value.play_rows[0].game_id === value.id
  )
}
/** 開始直後の一回読取用。記録後の内容を保存成功やReadyに昇格しない。

409（初球1件として返せない記録）は `recorded-unavailable` として値で返す。
*/
export async function readStartedGame(
  id: string,
  signal?: AbortSignal,
): Promise<StartedGameResult> {
  if (!uuid(id)) throw new Error('試合IDが正しくありません')
  let value: unknown
  try {
    value = await apiRequest<unknown>('GET', `/games/${id}/started`, {
      tenantBound: true,
      signal,
    })
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 404) return { kind: 'not-found' }
      if (error.status === 409) return { kind: 'recorded-unavailable' }
    }
    throw error
  }
  if (isStartedGame(value) && value.id === id)
    return { kind: 'found', game: value }
  if (isStartedRecordedGame(value) && value.id === id)
    return { kind: 'found', game: value }
  throw new Error('開始済み詳細の応答が不正です')
}

/** 普通投球の閉codecも同じ保存state/flag/旧T2の構造検査を再利用する。 */
export {
  state as isStartedGameStateSnapshot,
  timestamp as isStartedGameTimestamp,
  statFlags as isStartedGameStatFlags,
  t2 as isLegacyStartedT2,
}

/** 初球と同じ全公開列を保持し、普通投球の実位置だけを一般化する。 */
export type RecordedPrefixPlayRow = Readonly<
  Omit<StartedPlayRow, 'play_number' | 'batting_order'> & {
    play_number: number
    batting_order: number
  }
>
export type StartedGameMetadata = Omit<StartedGame, 'read_kind'>
/** 新projectionでも共通metadataを再計算せず同じ検証で読む。 */
export function isStartedGameMetadata(
  value: unknown,
): value is StartedGameMetadata & Record<string, unknown> {
  return object(value) && confirmedState(value)
}
export {
  ordinaryPlayRow as isRecordedPrefixPlayRow,
  INITIAL_KEYS as STARTED_GAME_BASE_KEYS,
}

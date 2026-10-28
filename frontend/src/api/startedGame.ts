import type {
  FieldingRoleWire,
  OneToNineDecimal,
  ProjectionWire,
} from '../../../contracts/state-transition/initial_game_roster_v1'
import type { StateSnapshot } from '../../../contracts/state-transition/t2_first_pitch_continuation_v1'
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
export type StartedGameResult =
  | { kind: 'found'; game: StartedGame }
  | { kind: 'not-found' }
  | { kind: 'recorded-unsupported' }

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
/** transportの閉じた形だけを検証する。計算・権利・Readyを判定しない。 */
export function isStartedGame(value: unknown): value is StartedGame {
  return (
    exact(value, [
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
    ]) &&
    value.read_kind === 'initial' &&
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
/** 開始直後の一回読取用。記録後409を保存成功やReadyに昇格しない。 */
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
      if (error.status === 409) return { kind: 'recorded-unsupported' }
    }
    throw error
  }
  if (!isStartedGame(value) || value.id !== id)
    throw new Error('開始済み詳細の応答が不正です')
  return { kind: 'found', game: value }
}

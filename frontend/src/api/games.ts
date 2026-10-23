import { canonicalUuid } from './authIntent'
import { apiRequest } from './client'

export type JsonValue =
  null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue }
export interface PreparingGame {
  id: string
  scheduled_at: string
  game_type_key: string
  tournament_key: string
  away_team_record_id: string
  home_team_record_id: string
  plate_umpire: string | null
  section_label: string | null
  week_label: string | null
  day_label: string | null
  game_number_label: string | null
  status: 'preparing'
  applied_rules: { [key: string]: JsonValue }
}
export interface PreparingPage {
  items: PreparingGame[]
  next_cursor: string | null
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function json(value: unknown): value is JsonValue {
  if (value === null || typeof value === 'string' || typeof value === 'boolean')
    return true
  if (typeof value === 'number') return Number.isFinite(value)
  if (Array.isArray(value)) return value.every(json)
  return object(value) && Object.values(value).every(json)
}
/** 業務規則を再検証せず、表示に渡すtransportの形だけを確認する。 */
export function isPreparingGame(value: unknown): value is PreparingGame {
  if (!object(value)) return false
  return (
    ['id', 'away_team_record_id', 'home_team_record_id'].every(
      (key) => typeof value[key] === 'string' && canonicalUuid.test(value[key]),
    ) &&
    typeof value.scheduled_at === 'string' &&
    /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value.scheduled_at) &&
    Number.isFinite(Date.parse(value.scheduled_at)) &&
    [
      'game_official',
      'game_semi_official',
      'game_open',
      'game_intrasquad',
      'game_other',
    ].includes(String(value.game_type_key)) &&
    typeof value.tournament_key === 'string' &&
    value.tournament_key.length > 0 &&
    [
      'plate_umpire',
      'section_label',
      'week_label',
      'day_label',
      'game_number_label',
    ].every((key) => value[key] === null || typeof value[key] === 'string') &&
    value.status === 'preparing' &&
    object(value.applied_rules) &&
    json(value.applied_rules)
  )
}
export async function listPreparingGames(
  cursor: string | null,
  signal?: AbortSignal,
): Promise<PreparingPage> {
  const value = await apiRequest<unknown>('GET', '/games', {
    tenantBound: true,
    signal,
    query: { limit: 20, cursor },
  })
  if (
    !object(value) ||
    !Array.isArray(value.items) ||
    value.items.length > 20 ||
    !value.items.every(isPreparingGame) ||
    !(
      value.next_cursor === null ||
      (typeof value.next_cursor === 'string' && value.next_cursor.length > 0)
    )
  )
    throw new Error('準備中一覧の応答が不正です')
  return value as unknown as PreparingPage
}
export async function readPreparingGame(
  id: string,
  signal?: AbortSignal,
): Promise<PreparingGame> {
  if (!canonicalUuid.test(id)) throw new Error('試合IDが正しくありません')
  const value = await apiRequest<unknown>('GET', `/games/${id}`, {
    tenantBound: true,
    signal,
  })
  if (!isPreparingGame(value) || value.id !== id)
    throw new Error('準備中詳細の応答が不正です')
  return value
}

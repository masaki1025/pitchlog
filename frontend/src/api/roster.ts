import { ApiError, apiRequest } from './client'
import type { Page, PageRequest } from './types'

export interface TeamRecordRead {
  id: string
  kind: 'self' | 'opponent'
  name: string
  hidden_at: string | null
}

export interface TeamRecordCreate {
  name: string
}

export interface TeamRecordUpdate {
  name: string
}

export type TeamRecordCreated = TeamRecordRead & { similar_names: string[] }

export interface PlayerRead {
  id: string
  team_record_id: string
  name: string
  throws: 'right' | 'left' | null
  bats: 'right' | 'left' | 'both' | null
  uniform_number: string | null
  roster_status_key: string
  roster_label_key: string | null
  hidden_at: string | null
}

export interface PlayerCreate {
  team_record_id: string
  name: string
  throws?: 'right' | 'left' | null
  bats?: 'right' | 'left' | 'both' | null
  uniform_number?: string | null
  roster_status_key: string
  roster_label_key?: string | null
}

export interface PlayerUpdate {
  name?: string
  throws?: 'right' | 'left' | null
  bats?: 'right' | 'left' | 'both' | null
  uniform_number?: string | null
}

export type PlayerCreated = PlayerRead & { same_number_players: PlayerRead[] }

export type PlayerListQuery = PageRequest & {
  team_record_id?: string
  roster_status_key?: string
  include_hidden?: boolean
}

export type TeamRecordListQuery = PageRequest & { include_hidden?: boolean }

interface RosterOptions {
  signal?: AbortSignal
}

const SELF_TEAM_FIELDS = ['hidden_at', 'id', 'kind', 'name'] as const
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isSelfTeamRecordRead(value: unknown): value is TeamRecordRead {
  if (
    typeof value !== 'object' ||
    value === null ||
    (Object.getPrototypeOf(value) !== Object.prototype &&
      Object.getPrototypeOf(value) !== null)
  )
    return false
  const record = value as Record<string, unknown>
  const fields = Object.keys(record).sort()
  return (
    fields.length === SELF_TEAM_FIELDS.length &&
    fields.every((field, index) => field === SELF_TEAM_FIELDS[index]) &&
    typeof record.id === 'string' &&
    UUID_PATTERN.test(record.id) &&
    record.kind === 'self' &&
    typeof record.name === 'string' &&
    record.hidden_at === null
  )
}

export async function readSelfTeamRecord(
  options?: RosterOptions,
): Promise<TeamRecordRead> {
  const result = await apiRequest<unknown>('GET', '/team-records/self', {
    signal: options?.signal,
    tenantBound: true,
  })
  if (!isSelfTeamRecordRead(result)) {
    throw new ApiError(
      200,
      '自チームの応答を確認できません',
      [],
      undefined,
      undefined,
    )
  }
  return result
}

export function listTeamRecords(
  query: TeamRecordListQuery,
  options?: RosterOptions,
): Promise<Page<TeamRecordRead>> {
  return apiRequest('GET', '/team-records', {
    query: { ...query },
    signal: options?.signal,
    tenantBound: true,
  })
}

export function createTeamRecord(
  body: TeamRecordCreate,
  options?: RosterOptions,
): Promise<TeamRecordCreated> {
  return apiRequest('POST', '/team-records', {
    body,
    signal: options?.signal,
    tenantBound: true,
  })
}

export function updateTeamRecord(
  id: string,
  body: TeamRecordUpdate,
  options?: RosterOptions,
): Promise<TeamRecordRead> {
  return apiRequest('PATCH', `/team-records/${encodeURIComponent(id)}`, {
    body,
    signal: options?.signal,
    tenantBound: true,
  })
}

export function hideTeamRecord(
  id: string,
  options?: RosterOptions,
): Promise<TeamRecordRead> {
  return apiRequest('DELETE', `/team-records/${encodeURIComponent(id)}`, {
    signal: options?.signal,
  })
}

export function listPlayers(
  query: PlayerListQuery,
  options?: RosterOptions,
): Promise<Page<PlayerRead>> {
  return apiRequest('GET', '/players', {
    query: { ...query },
    signal: options?.signal,
    tenantBound: true,
  })
}

export function getPlayer(
  id: string,
  options?: RosterOptions,
): Promise<PlayerRead> {
  return apiRequest('GET', `/players/${encodeURIComponent(id)}`, {
    signal: options?.signal,
    tenantBound: true,
  })
}

export function createPlayer(
  body: PlayerCreate,
  options?: RosterOptions,
): Promise<PlayerCreated> {
  return apiRequest('POST', '/players', {
    body,
    signal: options?.signal,
    tenantBound: true,
  })
}

export function updatePlayer(
  id: string,
  body: PlayerUpdate,
  options?: RosterOptions,
): Promise<PlayerRead> {
  return apiRequest('PATCH', `/players/${encodeURIComponent(id)}`, {
    body,
    signal: options?.signal,
    tenantBound: true,
  })
}

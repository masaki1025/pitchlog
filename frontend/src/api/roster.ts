import { apiRequest } from './client'
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

export function listTeamRecords(
  query: TeamRecordListQuery,
  options?: RosterOptions,
): Promise<Page<TeamRecordRead>> {
  return apiRequest('GET', '/team-records', {
    query: { ...query },
    signal: options?.signal,
  })
}

export function createTeamRecord(
  body: TeamRecordCreate,
  options?: RosterOptions,
): Promise<TeamRecordCreated> {
  return apiRequest('POST', '/team-records', { body, signal: options?.signal })
}

export function updateTeamRecord(
  id: string,
  body: TeamRecordUpdate,
  options?: RosterOptions,
): Promise<TeamRecordRead> {
  return apiRequest('PATCH', `/team-records/${encodeURIComponent(id)}`, {
    body,
    signal: options?.signal,
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
  })
}

export function getPlayer(
  id: string,
  options?: RosterOptions,
): Promise<PlayerRead> {
  return apiRequest('GET', `/players/${encodeURIComponent(id)}`, {
    signal: options?.signal,
  })
}

export function createPlayer(
  body: PlayerCreate,
  options?: RosterOptions,
): Promise<PlayerCreated> {
  return apiRequest('POST', '/players', { body, signal: options?.signal })
}

export function updatePlayer(
  id: string,
  body: PlayerUpdate,
  options?: RosterOptions,
): Promise<PlayerRead> {
  return apiRequest('PATCH', `/players/${encodeURIComponent(id)}`, {
    body,
    signal: options?.signal,
  })
}

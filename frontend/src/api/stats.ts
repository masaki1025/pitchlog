import { apiDownload, apiRequest } from './client'

export type StatState = 'available' | 'source_unavailable'
export type StatsCategory = 'official' | 'practice' | 'all'
export type GameStatsMode = 'current' | 'official'

export interface BasicStatItem {
  metric_id: string
  label: string
  state: StatState
  value: number | { numerator: string; denominator: string } | null
  display: string | null
  reason: string | null
  components: Record<string, unknown> | null
}

export interface PlayerBasicStats {
  player_id: string
  player_name: string
  uniform_number: string
  team_record_id: string
  team_name: string
  is_pitcher: boolean
  batting: BasicStatItem[]
  pitching: BasicStatItem[]
  pending: string[]
}

export interface GameBasicStats {
  game_id: string
  mode: GameStatsMode
  players: PlayerBasicStats[]
  next_cursor: string | null
}

export interface SeasonBasicStats {
  year: number
  category: StatsCategory
  period_label: string
  players: PlayerBasicStats[]
  next_cursor: string | null
}

export async function fetchGameStats(
  gameId: string,
  mode: GameStatsMode,
  signal?: AbortSignal,
  cursor?: string,
): Promise<GameBasicStats> {
  return apiRequest<GameBasicStats>('GET', `/games/${gameId}/stats`, {
    query: { mode, limit: 200, cursor },
    signal,
  })
}

export async function fetchSeasonStats(
  year: number,
  category: StatsCategory,
  signal?: AbortSignal,
  cursor?: string,
): Promise<SeasonBasicStats> {
  return apiRequest<SeasonBasicStats>('GET', `/stats/seasons/${year}`, {
    query: { category, limit: 200, cursor },
    signal,
  })
}

export async function downloadGameStatsCsv(
  gameId: string,
  mode: GameStatsMode,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiDownload(`/games/${gameId}/stats.csv`, { query: { mode } })
}

export async function downloadSeasonStatsCsv(
  year: number,
  category: StatsCategory,
): Promise<{ blob: Blob; filename: string | null }> {
  return apiDownload(`/stats/seasons/${year}/stats.csv`, {
    query: { category },
  })
}

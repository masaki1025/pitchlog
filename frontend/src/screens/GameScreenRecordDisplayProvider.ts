import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { StartedGameMetadata } from '../api/startedGame'
import {
  listPlayers,
  listTeamRecords,
  readSelfTeamRecord,
  type PlayerRead,
} from '../api/roster'
import { useAuthStore } from '../stores/authStore'

export type RecordPlayerView = Readonly<{
  id: string
  name: string
  number: string | null
  bats: 'right' | 'left' | 'both' | null
  throws: 'right' | 'left' | null
  teamRecordId: string
}>

/**
 * 記録画面のヘッダー表示に必要なチーム名・選手名だけを読む。
 * 取得できなくても記録操作は止めず、打順・守備位置の表示へ退避する。
 */
export function useRecordDisplay(game: Ref<StartedGameMetadata | null>) {
  const auth = useAuthStore()
  const teams = ref<ReadonlyMap<string, string>>(new Map())
  const players = ref<ReadonlyMap<string, RecordPlayerView>>(new Map())
  let sequence = 0
  let request: AbortController | null = null

  async function load() {
    const tenant = auth.teamId
    const epoch = auth.authEpoch
    if (!tenant || !auth.hasHydrated || !auth.isAuthenticated) {
      teams.value = new Map()
      players.value = new Map()
      return
    }
    const own = ++sequence
    request?.abort()
    request = new AbortController()
    const source = game.value
    try {
      const [page, self] = await Promise.all([
        listTeamRecords({ limit: 100 }, { signal: request.signal }),
        readSelfTeamRecord({ signal: request.signal }).catch(() => null),
      ])
      if (own !== sequence) return
      const teamNames = new Map(page.items.map((item) => [item.id, item.name]))
      if (self) teamNames.set(self.id, self.name)
      const ids = new Set<string>()
      if (source) {
        ids.add(source.away_team_record_id)
        ids.add(source.home_team_record_id)
      }
      const found = new Map<string, RecordPlayerView>()
      for (const teamId of ids) {
        try {
          const roster = await listPlayers(
            { team_record_id: teamId, limit: 100 },
            { signal: request.signal },
          )
          if (
            own !== sequence ||
            auth.teamId !== tenant ||
            auth.authEpoch !== epoch
          )
            return
          for (const player of roster.items) {
            if (player.hidden_at !== null) continue
            found.set(player.id, {
              id: player.id,
              name: player.name,
              number: player.uniform_number,
              bats: player.bats,
              throws: player.throws,
              teamRecordId: player.team_record_id,
            })
          }
        } catch {
          // 片方のチーム名簿を取得できなくても、他方の表示は維持する。
        }
      }
      if (own === sequence) {
        teams.value = teamNames
        players.value = found
      }
    } catch {
      if (own === sequence) {
        teams.value = new Map()
        players.value = new Map()
      }
    }
  }

  watch(
    () => [
      auth.teamId,
      auth.authEpoch,
      auth.hasHydrated,
      auth.isAuthenticated,
      game.value?.id,
      game.value?.away_team_record_id,
      game.value?.home_team_record_id,
    ],
    load,
    { immediate: true },
  )
  onScopeDispose(() => {
    sequence++
    request?.abort()
  })

  function player(id: string): RecordPlayerView | null {
    return players.value.get(id) ?? null
  }
  function playerName(id: string | null | undefined, fallback: string): string {
    if (!id) return fallback
    return players.value.get(id)?.name ?? fallback
  }
  function playerNumber(id: string | null | undefined): string | null {
    if (!id) return null
    return players.value.get(id)?.number ?? null
  }
  function teamName(id: string | null | undefined, fallback: string): string {
    if (!id) return fallback
    return teams.value.get(id) ?? fallback
  }
  const displayReady = computed(
    () => teams.value.size > 0 && players.value.size > 0,
  )
  return {
    teams,
    players,
    player,
    playerName,
    playerNumber,
    teamName,
    displayReady,
    reload: load,
  }
}

export type RecordDisplay = ReturnType<typeof useRecordDisplay>
export type { PlayerRead }

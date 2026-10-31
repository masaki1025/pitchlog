import { getActivePinia } from 'pinia'
import { nextTick, onScopeDispose, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import { ApiError } from '../api/client'
import {
  listPreparingGames,
  readPreparingGame,
  type PreparingGame,
} from '../api/games'
import { pinia } from '../appProviders'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../stores/authStore'
import type {
  EntrySupply,
  GameListPage,
  PreparingReadDetail,
} from './GameScreenEntryTypes'

function label(game: PreparingGame): string {
  return [
    game.scheduled_at,
    game.section_label,
    game.week_label,
    game.day_label,
    game.game_number_label,
    game.id,
  ]
    .filter((value) => value !== null && value !== '')
    .join(' / ')
}
function detail(game: PreparingGame, tenantId: string): PreparingReadDetail {
  return { gameId: game.id, tenantId, label: label(game), saved: game }
}
/** 正規QueryClientへ隔離した要求を登録し、認証・経路・要求世代の一致後だけ供給する。 */
export function usePreparingEntryProvider(kind: 'list' | 'detail') {
  const auth = useAuthStore(pinia)
  const route = useRoute()
  const page = shallowRef<EntrySupply<GameListPage> | null>(null)
  const preparing = shallowRef<EntrySupply<PreparingReadDetail> | null>(null)
  let sequence = 0
  let disposed = false
  let loading = false
  let cursor: string | null = null
  let history: (string | null)[] = [null]
  let historyIndex = 0
  // 同じ認証世代で複数hostが生きても他hostのqueryをcancelしない。
  const owner = crypto.randomUUID()
  function invalidateOwner(): void {
    sequence += 1
    loading = false
    // Cookie更新可能GETを中断せず、認証/tenant/epochの応答観測まで続ける。
    // 旧UIへの採用はcurrent()で拒否し、queryの掃除は完了後のfinallyだけで行う。
  }
  async function load(key: string | null): Promise<void> {
    invalidateOwner()
    const request = sequence
    const tenantId = auth.teamId
    const authEpoch = auth.authEpoch
    const path = route.path
    if (
      disposed ||
      getActivePinia() !== pinia ||
      !auth.hasHydrated ||
      !auth.isAuthenticated ||
      tenantId === null ||
      !canonicalUuid.test(tenantId)
    )
      return
    if (
      kind === 'list'
        ? path !== '/games'
        : !/^\/games\/[^/]+\/record$/.test(path)
    )
      return
    const id = route.params.gameId
    const requestKey = kind === 'list' ? key : typeof id === 'string' ? id : ''
    const base = { tenantId, authEpoch, path, requestKey }
    const current = () =>
      !disposed &&
      sequence === request &&
      getActivePinia() === pinia &&
      auth.hasHydrated &&
      auth.isAuthenticated &&
      auth.teamId === tenantId &&
      auth.authEpoch === authEpoch &&
      route.path === path &&
      (kind === 'list' || route.params.gameId === id)
    if (
      kind === 'detail' &&
      (typeof id !== 'string' || !canonicalUuid.test(id))
    ) {
      preparing.value = { ...base, status: 'denied' }
      return
    }
    loading = true
    if (kind === 'list') page.value = { ...base, status: 'pending' }
    else preparing.value = { ...base, status: 'pending' }
    const queryKey = [
      'preparing-read',
      owner,
      tenantId,
      authEpoch,
      path,
      requestKey,
      request,
    ] as const
    try {
      // fetchQueryはobserver/refetchを持たず、再実行は明示操作だけに限定する。
      const result = await queryClient.fetchQuery({
        queryKey,
        retry: false,
        staleTime: 0,
        gcTime: 0,
        queryFn: async ({ signal }) => {
          const value =
            kind === 'list'
              ? await listPreparingGames(key, signal)
              : await readPreparingGame(id as string, signal)
          if (!current() || signal.aborted)
            throw new Error('旧要求を破棄しました')
          return value
        },
      })
      if (!current()) return
      if (kind === 'list' && 'items' in result) {
        const existing = history.indexOf(key)
        if (existing >= 0) historyIndex = existing
        else {
          history = [...history.slice(0, historyIndex + 1), key]
          historyIndex += 1
        }
        const data: GameListPage = {
          items: result.items.map((game) => ({
            gameId: game.id,
            tenantId,
            label: label(game),
            stateLabel: '準備中',
          })),
          pageLabel: `${historyIndex + 1}ページ目`,
          previousKey: historyIndex > 0 ? history[historyIndex - 1]! : null,
          canPrevious: historyIndex > 0,
          nextKey: result.next_cursor,
        }
        if (current()) page.value = { ...base, status: 'ready', data }
      } else if (kind === 'detail' && 'id' in result) {
        const data = detail(result, tenantId)
        if (current()) preparing.value = { ...base, status: 'ready', data }
      }
    } catch (error) {
      if (!current()) return
      const status =
        error instanceof ApiError &&
        (error.status === 404 || error.status === 403)
          ? 'denied'
          : 'failed'
      if (kind === 'list') page.value = { ...base, status }
      else preparing.value = { ...base, status }
    } finally {
      queryClient.removeQueries({ queryKey, exact: true })
      if (sequence === request) {
        loading = false
      }
    }
  }
  function requestPage(key: string | null): void {
    if (loading) return
    if (
      key !== cursor &&
      !history.includes(key) &&
      key !== page.value?.data?.nextKey
    )
      return
    cursor = key
    void load(key)
  }
  function retry(): void {
    if (!loading) void load(cursor)
  }
  watch(
    () => [
      auth.authEpoch,
      auth.teamId,
      auth.isAuthenticated,
      auth.hasHydrated,
      route.path,
      route.params.gameId,
    ],
    () => {
      invalidateOwner()
      page.value = null
      preparing.value = null
      cursor = null
      history = [null]
      historyIndex = 0
      // 認証storeの一連の同期変更を終えてから通信を開始する。旧表示の破棄は同期で行う。
      const generation = sequence
      void nextTick(() => {
        if (!disposed && generation === sequence) void load(null)
      })
    },
    { immediate: true, flush: 'sync' },
  )
  onScopeDispose(() => {
    disposed = true
    invalidateOwner()
    page.value = null
    preparing.value = null
  })
  return { page, preparing, requestPage, retry }
}
